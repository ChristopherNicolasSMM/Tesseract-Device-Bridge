"""Compact staging identity and conservative Windows path-length preflight."""
import base64
import os
from pathlib import Path


class PathLengthError(OSError):
    code = 'setup_path_too_long'


def compact_attempt_name(attempt):
    # Encode all 128 UUID bits; never truncate identity or use case-sensitive
    # identifiers on Windows. Existing manifests keep their original layout.
    return base64.b32encode(bytes.fromhex(attempt)).decode('ascii').rstrip('=').lower()


def require_staging_budget(directory, *, windows=None):
    """Reserve room for the deepest imported name and SQLite journal filenames.

    54 filename units plus separator cover current compact i-/d-/q- jobs,
    source/validated copies, legacy uploads, ORM partial files and journals.
    No registry modification, prefix conversion or directory relocation.
    """
    if windows is None:
        windows = os.name == 'nt'
    if not windows:
        return
    projected = str(Path(directory).absolute() / ('x' * 54))
    if len(projected.encode('utf-16-le')) // 2 >= 260:
        raise PathLengthError(206, 'Setup staging path exceeds the Windows budget.', projected)
