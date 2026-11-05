"""Private, crash-resilient installer state, independent of the operational DB."""
from __future__ import annotations

import json
import re
import shutil
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
        from reusable.guided_setup.persistence import FileLock, LockError
        try:
            self.lock = FileLock(self.directory / 'lock')
        except LockError as exc:
            raise SetupError(str(exc)) from exc

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
        if (not isinstance(value, dict) or value.get("version") != 1 or value.get("status") not in ("new", "in_progress", "ready_simulated", "ready_operational", "needs_review")
                or value.get("language") not in ("pt_BR", "en")
                or (value.get("attempt") is not None
                    and (not isinstance(value["attempt"], str)
                         or not re.fullmatch(r"[0-9a-f]{32}", value["attempt"])))
                or (value.get("status") == "in_progress" and not value.get("attempt"))):
            raise SetupError("Unsupported or invalid installer state; preserve it for diagnosis.")
        return value

    def save(self, value):
        from reusable.guided_setup.persistence import atomic_json_write
        atomic_json_write(self.directory / 'state.json', value)
        self.value = value

    def start(self, language):
        if language not in ("pt_BR", "en"):
            raise SetupError("Unsupported language.")
        if self.value["status"] not in ("new", "in_progress"):
            raise SetupError("Installation already published. Use maintenance, not a new setup.")
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
        receipt = self.root / "data/private/installation.json"
        if receipt.exists() or receipt.is_symlink():
            error = SetupError("Publication exists. Recover or explicitly roll back before cancelling.")
            error.code = 'abort_publication_exists'
            raise error
        if self.value["status"] == "in_progress":
            path = self.staging()
            if path.exists():
                try:
                    shutil.rmtree(path)
                except OSError as exc:
                    error = SetupError('Temporary files could not be removed; close programs using them and retry.')
                    error.code = 'abort_files_busy'
                    raise error from exc
        self.save(dict(version=1, status="new", language=self.value["language"], attempt=None))
