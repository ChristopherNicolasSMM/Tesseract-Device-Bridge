"""Stable import events; never persist exception text or credentials."""
import json
import os
import tempfile
from functools import wraps
from pathlib import Path


def event(category, code, **fields):
    if category not in ('imported', 'warning', 'blocking_error', 'ignored'):
        raise ValueError('Invalid event category')
    return dict(category=category, code=code, **fields)


def save_report(directory, report):
    fd, temporary = tempfile.mkstemp(prefix='report-', suffix='.tmp', dir=str(directory))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, Path(directory) / 'report.json')
    finally:
        Path(temporary).unlink(missing_ok=True)


def record_import(function):
    @wraps(function)
    def run(state, *args, **kwargs):
        try:
            return function(state, *args, **kwargs)
        except Exception:
            # A failed job is diagnostic evidence, never an installable candidate.
            if state.value.get('status') == 'in_progress':
                job = Path(tempfile.mkdtemp(prefix='failed-', dir=str(state.staging())))
                save_report(job, dict(version=1, status='failed', database=None,
                    runtime_authorized=False, needs_review=True,
                    events=[event('blocking_error', 'import_failed')]))
            raise
    return run
