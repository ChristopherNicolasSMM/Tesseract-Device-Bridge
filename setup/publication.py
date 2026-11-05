"""Recoverable exclusive publication of a validated database and environment."""
import hashlib
import base64
import io
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
from contextlib import closing
from pathlib import Path

from dotenv import dotenv_values
from dotenv.parser import parse_stream

from .state import SetupError

FINAL_DB = 'data/private/bridge.sqlite3'
RECEIPT = 'data/private/installation.json'
FINAL_STATES = ('ready_simulated', 'ready_operational', 'needs_review')


class PublicationError(SetupError):
    def __init__(self, code='publish_invalid'):
        self.code = code
        super().__init__(code)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else _digest(stream)


def _digest(stream):
    result = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        result.update(chunk)
    return result.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix='receipt-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        sync_directory(path.parent)
    finally:
        Path(name).unlink(missing_ok=True)


def sync_directory(path):
    if os.name != 'nt':
        fd = os.open(str(path), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def owned(state, relative):
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise PublicationError()
    root = state.staging()
    path = root / relative
    if not path.resolve().is_relative_to(root):
        raise PublicationError()
    for item in [path] + list(path.parents):
        if item == root:
            break
        if item.is_symlink():
            raise PublicationError()
    if not path.is_file():
        raise PublicationError()
    return path


def candidates(state):
    if state.value['status'] != 'in_progress':
        return []
    result = []
    empty = state.staging() / 'bridge.sqlite3'
    if empty.is_file() and not empty.is_symlink():
        result.append(dict(id='bridge.sqlite3', label='clean', review=False))
    for report_path in sorted(state.staging().glob('*/report.json')):
        if report_path.is_symlink():
            continue
        report = json.loads(report_path.read_text(encoding='utf-8'))
        relative = report.get('database')
        if relative and report.get('status') == 'imported_staging':
            owned(state, relative)
            result.append(dict(id=relative, label=relative, review=bool(report.get('needs_review'))))
    return result


def validate_database(path):
    from config import BridgeConfig
    from recipe_engine.models import Recipe
    from storage.models import session_scope
    from storage.mappers import _config_from_orm
    from storage.repositories.orm import NormalizedRepository
    from control_settings import validate_settings
    from temperature_calibration import validate_calibrations
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as conn:
        if conn.execute('PRAGMA quick_check').fetchone()[0] != 'ok' or conn.execute('PRAGMA foreign_key_check').fetchall():
            raise PublicationError()
    repo = NormalizedRepository(path)
    with session_scope(path, readonly=True) as session:
        raw = _config_from_orm(session)
    parsed = BridgeConfig.from_dict(raw)
    recipes = repo.list_recipes()
    if raw['devices']:
        parsed.validate()
        for row in recipes:
            Recipe.from_dict(row['recipe']).validate(parsed)
        validate_calibrations(repo.calibrations(), parsed.devices)
    elif recipes or raw['backend'] != 'simulated':
        raise PublicationError()
    from storage.sqlite_store import DEFAULT_CONTROL_SETTINGS
    factory = repo.control_profile('control_factory')
    validate_settings(factory, defaults=DEFAULT_CONTROL_SETTINGS)
    validate_settings(repo.control_profile(), defaults=factory)
    session = repo.session_state() or {}
    return dict(devices=len(raw['devices']), recipes=len(recipes), backend=raw['backend'],
                session_pending=session.get('status') in ('ramping', 'holding', 'paused_manual', 'paused_after_crash'))


def exclusive_copy(source, target):
    # Never replace an existing DB. Runtime is blocked by the publication receipt
    # while a fallback copy is being written to the reserved final filename.
    target = Path(target)
    fd, name = tempfile.mkstemp(prefix='.publish-', dir=str(target.parent))
    try:
        with os.fdopen(fd, 'wb') as dest, Path(source).open('rb') as src:
            shutil.copyfileobj(src, dest)
            dest.flush()
            os.fsync(dest.fileno())
        # Same-filesystem hard link is atomic and fails if destination exists.
        # If unsupported, fail safely rather than exposing a partially copied DB.
        os.link(name, target)
        sync_directory(target.parent)
    finally:
        Path(name).unlink(missing_ok=True)


def rewrite_environment(text, install_id, force_simulation=False):
    result = ''
    for binding in parse_stream(io.StringIO(text)):
        if binding.error:
            raise PublicationError()
        if binding.key == 'TESSERACT_BRIDGE_INSTALL_ID':
            continue
        if force_simulation and binding.key == 'TESSERACT_BRIDGE_SIMULATION_ONLY':
            continue
        result += binding.original.string
    if result and not result.endswith('\n'):
        result += '\n'
    if force_simulation:
        result += 'TESSERACT_BRIDGE_SIMULATION_ONLY=1\n'
    return result + 'TESSERACT_BRIDGE_INSTALL_ID=' + install_id + '\n'


def validate_credential(settings):
    local = settings.get('TESSERACT_BRIDGE_LOCAL_ADMIN') == '1'
    encoded = settings.get('TESSERACT_BRIDGE_ADMIN_TOKEN_B64') or ''
    plain = settings.get('TESSERACT_BRIDGE_ADMIN_TOKEN') or ''
    try:
        token = base64.b64decode(encoded, validate=True).decode('utf-8') if encoded else plain
    except (ValueError, UnicodeError) as exc:
        raise PublicationError() from exc
    if (local and token) or (not local and not token):
        raise PublicationError()
    if token and (len(token.encode('utf-8')) > 4096 or any(c in token for c in ('\r', '\n', '\x00'))):
        raise PublicationError()


def check_physical_python():
    from tesseract_bridge.infrastructure.python_runtime import require_python39_for_real
    try:
        require_python39_for_real()
    except RuntimeError as exc:
        raise PublicationError('publish_python') from exc


def publish(state, candidate, *, replace_env=False, authorize_real=False):
    if state.value['status'] != 'in_progress':
        raise PublicationError()
    available = {item['id']: item for item in candidates(state)}
    if candidate not in available or not state.value.get('credential_configured'):
        raise PublicationError('publish_prepare_first')
    source = owned(state, candidate)
    security = owned(state, state.value.get('security_env'))
    summary = validate_database(source)
    text = security.read_text(encoding='utf-8')
    settings = dotenv_values(stream=io.StringIO(text), interpolate=False)
    validate_credential(settings)
    if (settings.get('TESSERACT_BRIDGE_DB') != './' + FINAL_DB
            or settings.get('TESSERACT_BRIDGE_STORAGE_MODE') != 'orm'
            or settings.get('TESSERACT_BRIDGE_SIMULATION_ONLY') not in ('0', '1')):
        raise PublicationError()
    from .infrastructure import validate, probe_port
    values = validate({key: settings.get('TESSERACT_BRIDGE_' + key, '') for key in
                       ('SIMULATION_ONLY', 'TEST_PANEL_PORT', 'PANEL_HOST', 'PANEL_PORT')})
    review = available[candidate]['review'] or summary['session_pending']
    selected_simulation = values['SIMULATION_ONLY'] == '1'
    if review or not summary['devices']:
        values['SIMULATION_ONLY'] = '1'
    probe_port(values, int(state.value.get('setup_port', 8090)))
    from .infrastructure import existing_env
    _, current_env_digest = existing_env(state.root)
    if current_env_digest != state.value.get('infrastructure_source_sha256'):
        raise PublicationError('publish_env_changed')
    if current_env_digest is not None and not replace_env:
        raise PublicationError('publish_replace_env')
    final_db = state.root / FINAL_DB
    receipt_path = state.root / RECEIPT
    if final_db.exists() or final_db.is_symlink() or receipt_path.exists() or receipt_path.is_symlink():
        raise PublicationError('publish_existing')
    simulated = selected_simulation
    target_status = 'needs_review' if review else 'ready_simulated'
    if not simulated and not review and summary['devices']:
        if not authorize_real:
            raise PublicationError('publish_authorize')
        if summary['backend'] == 'real':
            check_physical_python()
        target_status = 'ready_operational'
    job = Path(tempfile.mkdtemp(prefix='publish-', dir=str(state.staging())))
    prepared_db = job / 'database.sqlite3'
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src:
        with closing(sqlite3.connect(prepared_db)) as dest:
            src.backup(dest)
    prepared_db.chmod(0o600)
    identity = uuid.uuid4().int % 2147483646 + 1
    with closing(sqlite3.connect(prepared_db)) as conn:
        conn.execute('PRAGMA application_id=' + str(identity))
        conn.commit()
    validate_database(prepared_db)
    install_id = uuid.uuid4().hex
    env = job / 'new.env'
    fd = os.open(str(env), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(rewrite_environment(text, install_id, review or not summary['devices']))
        stream.flush()
        os.fsync(stream.fileno())
    if current_env_digest is not None:
        exclusive_copy(state.root / '.env', job / 'previous.env')
        if digest(job / 'previous.env') != current_env_digest:
            raise PublicationError('publish_env_changed')
    receipt = dict(version=1, id=install_id, status='publishing', target_status=target_status,
        database=FINAL_DB, database_identity=identity, database_sha256=digest(prepared_db),
        env_sha256=digest(env), previous_env_sha256=current_env_digest,
        job=job.relative_to(state.root).as_posix(), summary=summary)
    atomic_json(receipt_path, receipt)
    return recover(state)


def _publish_env(state, receipt, job):
    target = state.root / '.env'
    if target.is_symlink():
        raise PublicationError()
    current = digest(target) if target.exists() else None
    if current == receipt['env_sha256']:
        return
    if current != receipt['previous_env_sha256']:
        raise PublicationError('publish_env_changed')
    if current is None:
        exclusive_copy(job / 'new.env', target)
    else:
        # Explicit replacement only after the original was backed up and rechecked.
        fd, temp = tempfile.mkstemp(prefix='.setup-env-', dir=str(state.root))
        try:
            with os.fdopen(fd, 'wb') as dest, (job / 'new.env').open('rb') as src:
                shutil.copyfileobj(src, dest)
                dest.flush()
                os.fsync(dest.fileno())
            if digest(target) != current:
                raise PublicationError('publish_env_changed')
            os.replace(temp, target)
            sync_directory(state.root)
        finally:
            Path(temp).unlink(missing_ok=True)


def load_publication(state):
    path = state.root / RECEIPT
    if path.is_symlink():
        raise PublicationError()
    receipt = json.loads(path.read_text(encoding='utf-8'))
    if receipt.get('version') != 1 or receipt.get('database') != FINAL_DB:
        raise PublicationError()
    job = state.root / receipt.get('job', '')
    if (job.parent != state.staging() or not job.name.startswith('publish-')
            or not job.resolve().is_relative_to(state.staging()) or job.is_symlink()):
        raise PublicationError()
    return receipt, job


def recover(state):
    receipt, job = load_publication(state)
    if receipt['status'] in FINAL_STATES:
        state.save(dict(state.value, status=receipt['status'], published_id=receipt['id']))
        return receipt
    if receipt['status'] != 'publishing':
        raise PublicationError()
    for name, expected in (('database.sqlite3', receipt['database_sha256']), ('new.env', receipt['env_sha256'])):
        path = job / name
        if path.is_symlink() or not path.is_file() or digest(path) != expected:
            raise PublicationError()
    target = state.root / FINAL_DB
    if target.is_symlink() or any(Path(str(target) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
        raise PublicationError()
    if not target.exists():
        exclusive_copy(job / 'database.sqlite3', target)
    elif digest(target) != receipt['database_sha256']:
        raise PublicationError('publish_existing')
    _publish_env(state, receipt, job)
    receipt['status'] = receipt['target_status']
    atomic_json(state.root / RECEIPT, receipt)
    state.save(dict(state.value, status=receipt['status'], published_id=receipt['id']))
    return receipt


def rollback(state):
    receipt, job = load_publication(state)
    if receipt['status'] != 'publishing':
        raise PublicationError('publish_rollback_final')
    db, env = state.root / FINAL_DB, state.root / '.env'
    if db.is_symlink() or env.is_symlink() or any(Path(str(db) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
        raise PublicationError()
    if db.exists() and digest(db) != receipt['database_sha256']:
        raise PublicationError('publish_existing')
    current = digest(env) if env.exists() else None
    if current not in (None, receipt['previous_env_sha256'], receipt['env_sha256']):
        raise PublicationError('publish_env_changed')
    if current == receipt['env_sha256']:
        if receipt['previous_env_sha256'] is None:
            env.unlink()
        else:
            backup = job / 'previous.env'
            if backup.is_symlink() or digest(backup) != receipt['previous_env_sha256']:
                raise PublicationError()
            # Restore via a temporary file on the same filesystem.
            fd, name = tempfile.mkstemp(prefix='.restore-env-', dir=str(state.root))
            with os.fdopen(fd, 'wb') as dest, backup.open('rb') as src:
                shutil.copyfileobj(src, dest)
                dest.flush()
                os.fsync(dest.fileno())
            os.replace(name, env)
    if db.exists():
        db.unlink()
    (state.root / RECEIPT).unlink()
    sync_directory(state.root)
    state.save(dict(state.value, status='in_progress'))


def revalidate(state, *, authorize_real=False):
    receipt, job = load_publication(state)
    if receipt['status'] not in FINAL_STATES:
        raise PublicationError()
    target = state.root / FINAL_DB
    with closing(sqlite3.connect(target.as_uri() + '?mode=ro', uri=True)) as conn:
        if conn.execute('PRAGMA application_id').fetchone()[0] != receipt['database_identity']:
            raise PublicationError()
    summary = validate_database(target)
    if summary['session_pending']:
        raise PublicationError('publish_invalid')
    settings = dotenv_values(state.root / '.env', interpolate=False)
    validate_credential(settings)
    if settings.get('TESSERACT_BRIDGE_DB') != './' + FINAL_DB or settings.get('TESSERACT_BRIDGE_STORAGE_MODE') != 'orm':
        raise PublicationError()
    if settings.get('TESSERACT_BRIDGE_INSTALL_ID') != receipt['id']:
        raise PublicationError()
    from .infrastructure import validate, probe_port
    values = validate({key: settings.get('TESSERACT_BRIDGE_' + key, '') for key in
                       ('SIMULATION_ONLY', 'TEST_PANEL_PORT', 'PANEL_HOST', 'PANEL_PORT')})
    probe_port(values, int(state.value.get('setup_port', 8090)))
    simulated = values['SIMULATION_ONLY'] == '1'
    if not simulated and (not summary['devices'] or not authorize_real):
        raise PublicationError('publish_authorize')
    if not simulated and summary['backend'] == 'real':
        check_physical_python()
    receipt.update(status='ready_simulated' if simulated else 'ready_operational',
                   summary=summary, review_acknowledged=True)
    atomic_json(state.root / RECEIPT, receipt)
    state.save(dict(state.value, status=receipt['status']))
    return receipt
