"""Private single-process installer locking and crash-resilient JSON replacement."""
import json
import os
import tempfile
from pathlib import Path


class LockError(RuntimeError):
    pass


class FileLock:
    def __init__(self, path):
        path = Path(path)
        if path.is_symlink():
            raise LockError('Invalid setup lock.')
        self.stream = open(path, 'a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                self.stream.seek(0)
                if not self.stream.read(1):
                    self.stream.write(b'0')
                    self.stream.flush()
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.close()
            raise LockError('Another setup process is running.') from exc

    def close(self):
        if self.stream is not None:
            self.stream.close()
            self.stream = None


def atomic_json_write(path, value):
    """Host creates/checks the private parent and holds FileLock before calling.

    Does not create directories, interpret a schema or publish application data.
    """
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Linked state file rejected.')
    fd, name = tempfile.mkstemp(prefix='state-', suffix='.tmp', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        if os.name != 'nt':
            directory_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        Path(name).unlink(missing_ok=True)
