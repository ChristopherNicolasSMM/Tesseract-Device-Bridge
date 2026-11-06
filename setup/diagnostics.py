"""Project adapter for safe, persistent setup diagnostics."""
from .version import SETUP_BUILD


def logger(state):
    from reusable.guided_setup.diagnostics import DiagnosticLog
    value = getattr(state, '_diagnostics', None)
    if value is None:
        value = DiagnosticLog(state.directory / 'logs', project_root=state.root, build=SETUP_BUILD)
        state._diagnostics = value
    return value


def record(state, stage, status, *, exc=None, file_hint=None):
    existing = getattr(exc, '_setup_diagnostic_id', None) if exc is not None else None
    if existing:
        return existing
    try:
        event_id = logger(state).write(stage, status, exc=exc, file_hint=file_hint,
                                       attempt=state.value.get('attempt'))
        if exc is not None:
            state._last_diagnostic_error_id = event_id
            exc._setup_diagnostic_id = event_id
        return event_id
    except Exception:
        # Diagnostics cannot mask an import/cleanup error or create a candidate.
        return None


def checkpoint(state, stage, *, file_hint=None):
    state._diagnostic_context = dict(stage=stage, file_hint=file_hint)
    record(state, stage, 'started', file_hint=file_hint)
