"""Private, crash-resilient installer state, independent of the operational DB."""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path


class SetupError(RuntimeError):
    pass


class InstallationState:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.directory = self.root / "data" / "private" / "setup"
        # Do not follow pre-existing private directory links outside this clone.
        for directory in (self.root / "data", self.root / "data/private", self.directory):
            if directory.is_symlink():
                raise SetupError("Linked setup directories are not supported.")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = None
        self.acquire()
        try:
            self.value = self.read()
        except BaseException:
            self.close()
            raise

    def acquire(self):
        path = self.directory / "lock"
        if path.is_symlink():
            raise SetupError("Invalid setup lock.")
        self.lock = open(path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.lock.seek(0)
                if not self.lock.read(1):
                    self.lock.write(b"0")
                    self.lock.flush()
                self.lock.seek(0)
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.lock.close()
            self.lock = None
            raise SetupError("Another setup process is running.") from exc

    def close(self):
        if self.lock is not None:
            self.lock.close()
            self.lock = None

    def read(self):
        path = self.directory / "state.json"
        if path.is_symlink():
            raise SetupError("Invalid state file.")
        if not path.exists():
            return {"version": 1, "status": "new", "language": "pt_BR", "attempt": None}
        value = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(value, dict) or value.get("version") != 1 or value.get("status") not in ("new", "in_progress")
                or value.get("language") not in ("pt_BR", "en")
                or (value.get("attempt") is not None
                    and (not isinstance(value["attempt"], str)
                         or not re.fullmatch(r"[0-9a-f]{32}", value["attempt"])))
                or (value.get("status") == "in_progress" and not value.get("attempt"))):
            raise SetupError("Unsupported or invalid installer state; preserve it for diagnosis.")
        return value

    def save(self, value):
        fd, name = tempfile.mkstemp(prefix="state-", suffix=".tmp", dir=str(self.directory))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.directory / "state.json")
            if os.name != "nt":
                directory_fd = os.open(str(self.directory), os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            self.value = value
        finally:
            Path(name).unlink(missing_ok=True)

    def start(self, language):
        if language not in ("pt_BR", "en"):
            raise SetupError("Unsupported language.")
        value = dict(self.value, language=language)
        if value["status"] == "new":
            value.update(status="in_progress", attempt=uuid.uuid4().hex)
        # Persist ownership before creating staging, allowing recovery after a crash.
        self.save(value)
        self.staging().mkdir(mode=0o700, exist_ok=True)

    def staging(self):
        attempt = self.value.get("attempt")
        if not isinstance(attempt, str) or not re.fullmatch(r"[0-9a-f]{32}", attempt):
            raise SetupError("No valid installation attempt.")
        path = self.directory / ("attempt-" + attempt)
        if path.is_symlink():
            raise SetupError("Invalid staging directory.")
        return path

    def abort(self):
        if self.value["status"] == "in_progress":
            path = self.staging()
            if path.exists():
                shutil.rmtree(path)
        self.save(dict(version=1, status="new", language=self.value["language"], attempt=None))
