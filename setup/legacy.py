"""Bounded legacy discovery and private snapshot import. Never publishes a runtime DB."""
import hashlib
import json
import os
import tempfile
from pathlib import Path

from .state import SetupError
from .reports import event, record_import, save_report

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_ENTRIES = 1000


def _root(source):
    path = Path(source).expanduser()
    if path.is_symlink():
        raise SetupError('Linked source directory rejected.')
    root = path.resolve()
    if not root.is_dir():
        raise SetupError('Source directory does not exist.')
    return root


def _safe(root, relative):
    path = root / relative
    for part in [path] + list(path.parents):
        if part == root:
            break
        if part.is_symlink():
            raise SetupError('Linked source entries are not supported.')
    if not path.resolve().is_relative_to(root):
        raise SetupError('Source path escapes the selected directory.')
    return path


def discover(source):
    """Inspect known locations only; unknown files are listed, never executed."""
    from storage.legacy_import import LEGACY_FILES
    root = _root(source)
    known = set(LEGACY_FILES) | {'devices.yml'}
    candidates = set(known)
    for relative in ('.', 'data', 'data/public', 'data/private'):
        directory = _safe(root, relative)
        if directory.is_dir():
            for entry in directory.iterdir():
                candidates.add(entry.relative_to(root).as_posix())
                if len(candidates) > MAX_ENTRIES:
                    raise SetupError('Too many source entries.')
    rows = []
    for relative in sorted(candidates):
        path = _safe(root, relative)
        if path.is_file():
            size = path.stat().st_size
            rows.append({'path': relative, 'bytes': size,
                         'status': 'supported' if relative in known and size <= MAX_FILE_BYTES
                                   else 'too_large' if size > MAX_FILE_BYTES else 'ignored'})
    return rows


@record_import
def import_directory(state, source, *, selected=None, disable_invalid_remote_control=False,
                     allow_partial=False, _owned_upload=False, remote_state_topics=None):
    """Import selected YAML/JSON through legacy adapters into an independent ORM copy."""
    from storage.legacy_import import collect, import_snapshot, LEGACY_FILES
    from storage.orm_normalize import normalize_copy
    if state.value['status'] != 'in_progress':
        raise SetupError('Start an installation attempt first.')
    from .diagnostics import checkpoint, record
    checkpoint(state, 'legacy.discover')
    root = _root(source)
    staging = state.staging()
    owned = (_owned_upload and root.parent == staging and root.name.startswith('upload-'))
    if not owned and (root == state.root or root in staging.parents or staging == root or staging in root.parents):
        raise SetupError('Select a separate old installation, not the active clone or staging.')
    rows = discover(root)
    available = {row['path']: row for row in rows if row['status'] == 'supported'}
    chosen = set(available) if selected is None else set(selected)
    if not chosen <= available.keys():
        raise SetupError('Selection contains unsupported or missing files.')
    devices = chosen & {'devices.yml', 'data/public/devices.yml'}
    if len(devices) != 1:
        raise SetupError('Select exactly one devices.yml source.')
    if sum(available[name]['bytes'] for name in chosen) > MAX_TOTAL_BYTES:
        raise SetupError('Source exceeds import size limit.')
    checkpoint(state, 'legacy.staging')
    job = Path(tempfile.mkdtemp(prefix='import-', dir=str(staging)))
    snapshot_dir = job / 'source'
    snapshot_dir.mkdir(mode=0o700)
    hashes = {}
    # All parsers consume private copies; original paths never reach the importer.
    for relative in sorted(chosen):
        checkpoint(state, 'legacy.capture', file_hint=relative)
        path = _safe(root, relative)
        with path.open('rb') as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise SetupError('Source file exceeds size limit.')
        digest = hashlib.sha256(raw).hexdigest()
        with path.open('rb') as stream:
            repeated = stream.read(MAX_FILE_BYTES + 1)
        if hashlib.sha256(repeated).hexdigest() != digest:
            raise SetupError('Source changed during capture. Stop the old Bridge and retry.')
        target = snapshot_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(target), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
        hashes[relative] = digest
    checkpoint(state, 'legacy.validate')
    if allow_partial:
        from .partial import collect_partial
        snapshot, events = collect_partial(snapshot_dir, next(iter(devices)),
            disable_invalid_remote_control=disable_invalid_remote_control, remote_state_topics=remote_state_topics, state=state)
    else:
        from .partial import devices_error_code
        from storage.legacy_import import _normalize_legacy_config
        import yaml
        devices_file = next(iter(devices))
        try:
            with (snapshot_dir / devices_file).open(encoding='utf-8') as stream:
                _normalize_legacy_config(yaml.safe_load(stream) or {},
                    disable_invalid_remote_control=disable_invalid_remote_control, remote_state_topics=remote_state_topics)
        except Exception as exc:
            record(state, 'legacy.devices', 'error', exc=exc, file_hint=devices_file)
            snapshot = None
            events = [event('blocking_error', devices_error_code(exc), file=devices_file)]
        else:
            snapshot = collect(snapshot_dir, devices_file=devices_file,
                disable_invalid_remote_control=disable_invalid_remote_control, remote_state_topics=remote_state_topics)
            events = [event('imported', 'legacy_validated')]
    if snapshot is None:
        report = dict(version=1, status='needs_review', database=None, files=hashes,
                      diagnostic_id=getattr(state, '_last_diagnostic_error_id', None),
                      needs_review=True, runtime_authorized=False, events=events)
        if any(e['code'] in ('devices_remote_invalid', 'devices_remote_topic_invalid') for e in events):
            import yaml
            from storage.legacy_import import _needs_remote_disable
            raw = yaml.safe_load((snapshot_dir / next(iter(devices))).read_text(encoding='utf-8'))
            report['remote_conflicts'] = [dict(id=d['id'], name=d.get('name', d['id']))
                for d in raw.get('devices', []) if _needs_remote_disable(d)]
        checkpoint(state, 'report.persist')
        save_report(job, report)
        return report
    intermediate = job / 'legacy.sqlite3'
    from .reports import failure_report
    checkpoint(state, 'legacy.write')
    try:
        import_snapshot(snapshot, destination=intermediate)
    except Exception as exc:
        report = failure_report('legacy_write_failed', exc, events=events, state=state)
        checkpoint(state, 'report.persist')
        save_report(job, report)
        return report
    target = job / 'bridge.sqlite3'
    checkpoint(state, 'legacy.normalize')
    try:
        normalize_copy(source=intermediate, destination=target)
    except Exception as exc:
        report = failure_report('orm_conversion_failed', exc, events=events, state=state)
        checkpoint(state, 'report.persist')
        save_report(job, report)
        return report
    report = {'version': 1, 'status': 'imported_staging', 'database': str(target.relative_to(staging)),
              'files': hashes, 'counts': snapshot['counts'], 'repairs': snapshot['repairs'],
              'diagnostic_id': getattr(state, '_last_diagnostic_error_id', None),
              'ignored': [row['path'] for row in rows if row['path'] not in chosen],
              'runtime_authorized': False,
              'needs_review': bool(snapshot['repairs']) or any(e['category'] in ('warning', 'blocking_error') for e in events),
              'events': events + [event('ignored', 'file_ignored', file=row['path'])
                                  for row in rows if row['path'] not in chosen
                                  and row['path'] in set(LEGACY_FILES) | {'devices.yml'}]}
    checkpoint(state, 'report.persist')
    save_report(job, report)
    return report
