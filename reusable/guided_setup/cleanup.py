"""Delete an explicitly owned staging tree, including Windows read-only files.

No traversal of linked targets, process termination or operational-file cleanup.
The caller verifies ownership and publication state before invoking this helper.
"""
import os
import shutil
import stat
from pathlib import Path


def remove_staging_tree(directory):
    root = Path(directory).absolute()
    if root.is_symlink() or getattr(root, 'is_junction', lambda: False)():
        raise OSError('Linked staging directory rejected.')

    def retry_readonly(operation, filename, exc_info):
        exc = exc_info[1]
        path = Path(filename).absolute()
        # Retry only deletion of owned entries, never arbitrary callback actions.
        if (not isinstance(exc, PermissionError) or operation not in (os.unlink, os.remove, os.rmdir)
                or not path.is_relative_to(root) or path.is_symlink()
                or getattr(path, 'is_junction', lambda: False)()):
            raise exc
        for parent in path.parents:
            if parent == root:
                break
            if parent.is_symlink() or getattr(parent, 'is_junction', lambda: False)():
                raise exc
        # On Windows chmod controls the read-only attribute. Do not use it to
        # bypass a sharing violation: a genuinely open handle still fails here.
        path.chmod(path.stat().st_mode | stat.S_IWUSR)
        operation(filename)

    shutil.rmtree(root, onerror=retry_readonly)
