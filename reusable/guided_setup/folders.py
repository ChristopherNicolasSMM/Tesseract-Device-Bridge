"""Read-only folder navigation for a locally authorized installer.

Returns directory names only, never file contents. The HTTP/authentication boundary
belongs to the host. No database, GUI, shell, DNS or hardware dependency.
"""
import os
from pathlib import Path


class FolderError(ValueError):
    pass


def roots():
    """Filesystem roots; Windows drive bitmap avoids probing network volumes."""
    if os.name == 'nt':
        import ctypes
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        return [chr(65 + n) + ':\\' for n in range(26) if mask & (1 << n)]
    return ['/']


def list_folders(path='', *, limit=200, scan_limit=2000):
    if not isinstance(path, str) or len(path) > 2048 or '\x00' in path:
        raise FolderError('folder_invalid')
    try:
        selected = Path(path).expanduser() if path else Path.home()
        if selected.is_symlink() or not selected.is_dir():
            raise FolderError('folder_unavailable')
        selected = selected.resolve()
        children = []
        truncated = False
        with os.scandir(selected) as entries:
            for index, entry in enumerate(entries):
                if index >= scan_limit:
                    truncated = True
                    break
                if entry.name.startswith('.') or entry.name in ('__pycache__', 'venv', 'node_modules'):
                    continue
                try:
                    if not entry.is_symlink() and entry.is_dir(follow_symlinks=False):
                        children.append(dict(name=entry.name, path=str(selected / entry.name)))
                        if len(children) >= limit:
                            truncated = True
                            break
                except OSError:
                    continue
        children.sort(key=lambda entry: entry['name'].casefold())
        return dict(path=str(selected), parent=str(selected.parent) if selected.parent != selected else None,
                    folders=children, roots=roots(), truncated=truncated)
    except (OSError, RuntimeError, ValueError) as exc:
        if isinstance(exc, FolderError):
            raise
        raise FolderError('folder_unavailable') from exc
