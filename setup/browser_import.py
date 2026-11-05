"""Browser adapter for bounded discovery, private uploads and import review."""
import json
import os
import re
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path, PurePosixPath

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, session

from .i18n import catalog, translate_report
from .state import SetupError

bp = Blueprint('setup_import', __name__, url_prefix='/import')
PREVIEW_INPUT = 256 * 1024
PREVIEW_OUTPUT = 64 * 1024
SECRET = re.compile(r'password|passwd|secret|token|credential|api.?key|authorization', re.I)


def redact(value, depth=0, budget=None, seen=None):
    budget = [20000] if budget is None else budget
    seen = set() if seen is None else seen
    budget[0] -= 1
    if depth > 32 or budget[0] < 0:
        raise SetupError('Preview structure exceeds limits.')
    if isinstance(value, (dict, list)):
        if id(value) in seen:
            raise SetupError('Recursive preview rejected.')
        seen = seen | {id(value)}
    if isinstance(value, dict):
        return {str(k): '[REDACTED]' if SECRET.search(str(k)) else
                redact(v, depth + 1, budget, seen) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, depth + 1, budget, seen) for v in value]
    return value


def parse_preview(path):
    import yaml
    if path.stat().st_size > PREVIEW_INPUT:
        return {'text': '', 'code': 'preview_large', 'count': None}
    with path.open('rb') as stream:
        raw = stream.read(PREVIEW_INPUT + 1)
    if len(raw) > PREVIEW_INPUT:
        return {'text': '', 'code': 'preview_large', 'count': None}
    if path.suffix.lower() == '.txt':
        value = raw.decode('utf-8')
    elif path.suffix.lower() == '.json':
        value = json.loads(raw.decode('utf-8'))
    else:
        value = yaml.safe_load(raw.decode('utf-8'))
    safe = redact(value)
    count = len(safe.get('devices', [])) if isinstance(safe, dict) and 'devices' in safe else len(safe) if isinstance(safe, list) else 1
    text = (yaml.safe_dump(safe, allow_unicode=True, sort_keys=False)
            if path.suffix.lower() in ('.yaml', '.yml') else
            json.dumps(safe, ensure_ascii=False, indent=2, default=str))
    return {'text': text[:PREVIEW_OUTPUT], 'count': count,
            'code': 'preview_truncated' if len(text) > PREVIEW_OUTPUT else 'preview_ready'}


def state():
    value = current_app.extensions['installation_state']
    if value.value['status'] != 'in_progress':
        raise SetupError('Start installation first.')
    return value


def descriptor():
    value = state()
    desc = value.value.get('browser_source')
    if not isinstance(desc, dict):
        raise SetupError('Choose an import source.')
    return value, desc


def remember(value, desc):
    # Source descriptions live server-side in the private manifest, never in cookies.
    value.save(dict(value.value, browser_source=desc, browser_report=None))


def inventory_rows(root):
    from .legacy import discover, _safe
    from storage.legacy_import import LEGACY_FILES
    known = set(LEGACY_FILES) | {'devices.yml'}
    # Keep unknown entries in the engine/report, not in the selectable browser grid.
    rows = [row for row in discover(root) if row['path'] in known]
    for index, row in enumerate(rows):
        row.update(id=str(index), format=Path(row['path']).suffix.lstrip('.'), count=None)
        if row['status'] == 'supported':
            try:
                result = parse_preview(_safe(root, row['path']))
                row['count'] = result['count']
                if result['code'] == 'preview_large':
                    row['preview_code'] = 'preview_large'
            except Exception:
                row['preview_code'] = 'preview_invalid'
    return rows


def sqlite_source(value, path):
    from .sqlite_import import capture, inspect
    job = Path(tempfile.mkdtemp(prefix='sqlite-source-', dir=str(value.staging())))
    copied = job / 'source.sqlite3'
    capture(path, copied)
    kind, revision = inspect(copied)
    with closing(sqlite3.connect(copied.as_uri() + '?mode=ro', uri=True)) as conn:
        table = 'bridge_devices_v2' if kind == 'orm' else 'devices'
        count = conn.execute('SELECT count(*) FROM ' + table).fetchone()[0]
    remember(value, {'kind': 'sqlite', 'root': str(copied),
        'rows': [dict(id='0', path=Path(path).name, bytes=copied.stat().st_size,
                      format='sqlite', status='supported', count=count)],
        'metadata': dict(kind=kind, revision=revision, devices=count)})


@bp.get('/')
def page():
    value = state()
    session.setdefault('csrf', __import__('secrets').token_urlsafe(32))
    language = value.value['language']
    report = value.value.get('browser_report')
    source = value.value.get('browser_source')
    if source and source.get('kind') != 'sqlite':
        from storage.legacy_import import LEGACY_FILES
        known = set(LEGACY_FILES) | {'devices.yml'}
        # Resumed attempts may contain an inventory written by an older build.
        source = dict(source, rows=[row for row in source['rows'] if row['path'] in known])
    return render_template('import.html', t=catalog(language), language=language,
        theme=value.value.get('theme', 'light'), csrf=session['csrf'],
        source=source, report=translate_report(report, language) if report else None,
        build=current_app.config['SETUP_BUILD'])


@bp.post('/folders')
def browse_folders():
    from reusable.guided_setup.folders import list_folders, FolderError
    value = state()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        abort(400)
    try:
        return jsonify(list_folders(payload.get('path', '')))
    except FolderError as exc:
        code = str(exc)
        return jsonify(code=code, message=catalog(value.value['language'])[code]), 409


@bp.post('/discover')
def discover_source():
    from .legacy import _root
    value = state()
    path = request.form.get('source', '').strip()
    if len(path) >= 2 and path[0] == path[-1] == '"':
        path = path[1:-1]
    if not path or len(path) > 2048:
        raise SetupError('Choose a source.')
    if request.form.get('kind') == 'sqlite':
        sqlite_source(value, path)
    elif request.form.get('kind') == 'directory':
        root = _root(path)
        if root == value.root or root.is_relative_to(value.root) or value.root.is_relative_to(root):
            raise SetupError('Select the old installation, not the new clone.')
        remember(value, dict(kind='directory', root=str(root), rows=inventory_rows(root)))
    else:
        raise SetupError('Unsupported source type.')
    return redirect('/import/', code=303)


@bp.post('/upload')
def upload_source():
    from .uploads import capture_uploads
    from .legacy import MAX_FILE_BYTES, MAX_TOTAL_BYTES
    from .sqlite_import import MAX_DB_BYTES
    from storage.legacy_import import LEGACY_FILES
    value = state()
    uploads = request.files.getlist('files')
    if not uploads or len(uploads) > 100:
        raise SetupError('Invalid upload set.')
    if request.form.get('kind') == 'sqlite':
        if len(uploads) != 1:
            raise SetupError('Choose exactly one SQLite file.')
        if Path(uploads[0].filename or '').suffix.lower() not in ('.sqlite3', '.sqlite', '.db'):
            raise SetupError('Invalid SQLite upload extension.')
        job = Path(tempfile.mkdtemp(prefix='sqlite-upload-', dir=str(value.staging())))
        target = job / 'uploaded.sqlite3'
        total = 0
        with target.open('xb') as stream:
            while True:
                chunk = uploads[0].stream.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DB_BYTES:
                    raise SetupError('SQLite exceeds limit.')
                stream.write(chunk)
        target.chmod(0o600)
        sqlite_source(value, target)
        return redirect('/import/', code=303)
    known = set(LEGACY_FILES) | {'devices.yml'}
    captured = {}
    total = 0
    destination = request.form.get('destination', '')
    for upload in uploads:
        name = upload.filename or ''
        if PurePosixPath(name).suffix.lower() not in ('.yaml', '.yml', '.json', '.txt'):
            raise SetupError('Invalid legacy upload extension.')
        if '\\' in name or '..' in PurePosixPath(name).parts or PurePosixPath(name).is_absolute():
            raise SetupError('Invalid upload path.')
        if destination:
            if len(uploads) != 1:
                raise SetupError('Explicit mapping requires one file.')
            name = destination
        elif name not in known:
            parts = name.split('/')
            # Browser directory upload prepends the selected folder name.
            candidate = '/'.join(parts[1:]) if len(parts) > 1 else ''
            if candidate in known:
                name = candidate
            else:
                matches = [p for p in known if Path(p).name == name]
                if len(matches) != 1:
                    raise SetupError('Ambiguous file; select its destination explicitly.')
                name = matches[0]
        if name not in known or name in captured:
            raise SetupError('Unsupported or duplicate upload destination.')
        raw = upload.stream.read(MAX_FILE_BYTES + 1)
        total += len(raw)
        if len(raw) > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
            raise SetupError('Upload exceeds limit.')
        captured[name] = raw
    previous = value.value.get('browser_source') or {}
    if previous.get('kind') == 'upload':
        from .legacy import _root, _safe, discover
        previous_root = _root(previous['root'])
        if previous_root.parent != value.staging() or not previous_root.name.startswith('upload-'):
            raise SetupError('Previous upload does not belong to this attempt.')
        for row in discover(previous_root):
            if row['status'] != 'supported':
                raise SetupError('Previous upload is no longer valid.')
            name = row['path']
            if name in captured:
                raise SetupError('Duplicate upload destination; choose a new source explicitly.')
            with _safe(previous_root, name).open('rb') as stream:
                captured[name] = stream.read(MAX_FILE_BYTES + 1)
    # Recheck total/file limits after combining all private uploads.
    root = capture_uploads(value, captured)
    remember(value, dict(kind='upload', root=str(root), rows=inventory_rows(root)))
    return redirect('/import/', code=303)


@bp.get('/preview/<entry_id>')
def preview(entry_id):
    from .legacy import _safe
    value, desc = descriptor()
    row = next((r for r in desc['rows'] if r['id'] == entry_id), None)
    if row is None or row['status'] != 'supported':
        abort(404)
    if desc['kind'] == 'sqlite':
        return jsonify(text=json.dumps(desc['metadata'], indent=2), code='preview_ready', count=row['count'])
    try:
        result = parse_preview(_safe(Path(desc['root']), row['path']))
    except Exception:
        # Never show raw malformed text: credentials may be embedded in it.
        result = dict(text='', code='preview_invalid', count=None)
    return jsonify(result)


@bp.post('/run')
def run_import():
    value, desc = descriptor()
    selected = request.form.getlist('selected')
    allowed = {row['id']: row['path'] for row in desc['rows'] if row['status'] == 'supported'}
    if not selected or not set(selected) <= allowed.keys():
        raise SetupError('Select supported files.')
    try:
        if desc['kind'] == 'sqlite':
            from .sqlite_import import import_sqlite
            report = import_sqlite(value, desc['root'], _owned_capture=True)
        else:
            from .legacy import import_directory
            report = import_directory(value, desc['root'], selected=[allowed[key] for key in selected],
                allow_partial=request.form.get('allow_partial') == '1',
                _owned_upload=desc['kind'] == 'upload')
    except Exception:
        report = dict(status='failed', database=None, needs_review=True, runtime_authorized=False,
                      events=[dict(category='blocking_error', code='import_failed')])
    value.save(dict(value.value, browser_report=report, browser_acknowledged=False))
    return redirect('/import/', code=303)


@bp.post('/acknowledge')
def acknowledge():
    value = state()
    report = value.value.get('browser_report') or {}
    if not report.get('database') or report.get('status') == 'failed':
        raise SetupError('No valid candidate.')
    # This acknowledges review only; it is never an operational readiness flag.
    value.save(dict(value.value, browser_acknowledged=True))
    session['notice'] = 'review_saved'
    return redirect('/infrastructure/', code=303)
