"""Bounded JSONL diagnostics without exception messages, source text or locals.

Each write closes its file. The host supplies a private directory and holds the
installation process lock. Logs are independent of disposable staging attempts.
"""
import json
import os
import threading
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path


class DiagnosticLog:
    def __init__(self, directory, *, project_root, build, max_bytes=1024 * 1024, backups=2):
        self.directory = Path(directory)
        self.project_root = Path(project_root).resolve()
        self.build = build
        self.max_bytes = max_bytes
        self.backups = backups
        self.lock = threading.RLock()

    def _paths(self):
        for path in (self.directory, *self.directory.parents):
            if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
                raise OSError('Linked diagnostic directory rejected.')
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        paths = [self.directory / ('setup.jsonl' + ('.' + str(i) if i else ''))
                 for i in range(self.backups + 1)]
        if any(p.is_symlink() or (p.exists() and not p.is_file()) for p in paths):
            raise OSError('Invalid diagnostic file.')
        return paths

    def _exception(self, exc, depth=0):
        result = dict(type=type(exc).__name__, frames=[])
        for key in ('errno', 'winerror', 'sqlite_errorcode'):
            value = getattr(exc, key, None)
            if isinstance(value, int):
                result[key] = value
        filename = getattr(exc, 'filename', None)
        if filename is not None:
            result['path_length'] = len(str(filename))
        # Frame coordinates only: never formatted traceback lines or locals.
        for frame in traceback.extract_tb(exc.__traceback__)[-16:]:
            path = Path(frame.filename)
            try:
                name = path.resolve().relative_to(self.project_root).as_posix()
            except ValueError:
                name = path.name
            result['frames'].append(dict(file=name, line=frame.lineno, function=frame.name))
        cause = exc.__cause__ or exc.__context__
        if cause is not None and cause is not exc and depth < 2:
            result['cause'] = self._exception(cause, depth + 1)
        return result

    def write(self, stage, status, *, exc=None, file_hint=None, attempt=None):
        event_id = uuid.uuid4().hex
        record = dict(version=1, event_id=event_id, timestamp=datetime.now(timezone.utc).isoformat(),
                      build=self.build, stage=stage, status=status, attempt=attempt)
        if file_hint:
            record['file'] = file_hint
        if exc is not None:
            record['exception'] = self._exception(exc)
        raw = (json.dumps(record, ensure_ascii=False) + '\n').encode('utf-8')
        if len(raw) > self.max_bytes:
            raise OSError('Diagnostic entry exceeds limit.')
        with self.lock:
            paths = self._paths()
            if paths[0].exists() and paths[0].stat().st_size + len(raw) > self.max_bytes:
                for i in range(self.backups, 0, -1):
                    if paths[i - 1].exists():
                        os.replace(paths[i - 1], paths[i])
            fd = os.open(str(paths[0]), os.O_CREAT | os.O_APPEND | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            with os.fdopen(fd, 'ab') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        return event_id

    def read_all(self):
        with self.lock:
            chunks = []
            for path in reversed(self._paths()):
                if path.exists():
                    with path.open('rb') as stream:
                        chunks.append(stream.read(self.max_bytes))
            return b''.join(chunks)
