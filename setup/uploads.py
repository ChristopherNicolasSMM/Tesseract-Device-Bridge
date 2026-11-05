"""Safe byte-upload contract for the upcoming HTTP wizard; no HTTP routes yet."""
import os
import tempfile
from pathlib import Path, PurePosixPath

from .state import SetupError


def capture_uploads(state, files):
    from storage.legacy_import import LEGACY_FILES
    from .legacy import MAX_FILE_BYTES, MAX_TOTAL_BYTES
    if state.value['status'] != 'in_progress':
        raise SetupError('Start an installation attempt first.')
    known = set(LEGACY_FILES) | {'devices.yml'}
    if not isinstance(files, dict) or not files or len(files) > len(known):
        raise SetupError('Invalid upload set.')
    total = 0
    for name, content in files.items():
        if (not isinstance(name, str) or '\\' in name or name not in known
                or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts
                or not isinstance(content, bytes) or len(content) > MAX_FILE_BYTES):
            raise SetupError('Invalid upload path, format or size.')
        total += len(content)
    if total > MAX_TOTAL_BYTES:
        raise SetupError('Upload exceeds total size limit.')
    root = Path(tempfile.mkdtemp(prefix='upload-', dir=str(state.staging())))
    for name, content in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(target), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
    return root


def import_uploads(state, files, **options):
    from .legacy import import_directory
    source = capture_uploads(state, files)
    return import_directory(state, source, _owned_upload=True, **options)
