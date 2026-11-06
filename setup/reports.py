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
        from .diagnostics import checkpoint, record
        previous = getattr(state, '_diagnostic_context', None)
        state._last_diagnostic_error_id = None
        checkpoint(state, function.__name__)
        try:
            report = function(state, *args, **kwargs)
            record(state, function.__name__, report.get('status', 'completed'))
            return report
        except Exception as exc:
            context = getattr(state, '_diagnostic_context', {})
            event_id = record(state, context.get('stage', function.__name__), 'error', exc=exc,
                              file_hint=context.get('file_hint'))
            # A second filesystem failure must not replace the original cause.
            try:
                if state.value.get('status') == 'in_progress':
                    job = Path(tempfile.mkdtemp(prefix='failed-', dir=str(state.staging())))
                    save_report(job, dict(version=1, status='failed', database=None,
                        diagnostic_id=event_id, runtime_authorized=False, needs_review=True,
                        events=[event('blocking_error', 'import_failed')]))
            except OSError as save_exc:
                record(state, 'report.persist', 'error', exc=save_exc)
            raise
        finally:
            state._diagnostic_context = previous
    return run


def failure_report(stage, exc, *, events=(), state=None):
    """Static diagnostics only; exception messages can contain imported secrets."""
    import sqlite3
    from storage.mappers import NormalizationError
    if isinstance(exc, PermissionError):
        reason = 'import_permission_error'
    elif isinstance(exc, sqlite3.IntegrityError):
        reason = 'import_integrity_error'
    elif isinstance(exc, sqlite3.Error):
        reason = 'import_sqlite_error'
    elif isinstance(exc, NormalizationError):
        reason = 'import_mapping_error'
    elif isinstance(exc, (KeyError, TypeError, ValueError)):
        reason = 'import_structure_error'
    elif isinstance(exc, OSError):
        reason = 'import_filesystem_error'
    else:
        reason = 'import_internal_error'
    from .diagnostics import record
    event_id = record(state, stage, 'error', exc=exc) if state is not None else None
    return dict(version=1, status='failed', database=None, needs_review=True, diagnostic_id=event_id,
                runtime_authorized=False,
                events=list(events) + [event('blocking_error', stage),
                                      event('blocking_error', reason)])
