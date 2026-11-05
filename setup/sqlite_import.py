"""Import a quiescent SQLite snapshot without opening the original for writes."""
import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from .state import SetupError
from .reports import event, record_import, save_report

MAX_DB_BYTES = 256 * 1024 * 1024


def capture(source, destination):
    source = Path(source).expanduser()
    if source.is_symlink() or any(p.is_symlink() for p in source.parents):
        raise SetupError('Linked SQLite paths are not supported.')
    source = source.resolve()
    if not source.is_file() or source.stat().st_size > MAX_DB_BYTES:
        raise SetupError('SQLite source missing or too large.')
    # Do not ignore committed WAL contents or run recovery against the old installation.
    for suffix in ('-wal', '-shm', '-journal'):
        if Path(str(source) + suffix).exists():
            raise SetupError('SQLite sidecars found. Stop the old Bridge and supply a clean checkpointed backup.')
    with source.open('rb') as stream:
        if stream.read(16) != b'SQLite format 3\x00':
            raise SetupError('Not a SQLite database.')
    before = source.stat()
    digest = hashlib.sha256()
    fd = os.open(str(destination), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as target, source.open('rb') as stream:
        total = 0
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_DB_BYTES:
                raise SetupError('SQLite exceeds size limit.')
            digest.update(chunk)
            target.write(chunk)
        target.flush()
        os.fsync(target.fileno())
    repeated = hashlib.sha256()
    with source.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            repeated.update(chunk)
    after = source.stat()
    if ((before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
            or digest.digest() != repeated.digest()
            or any(Path(str(source) + s).exists() for s in ('-wal', '-shm', '-journal'))):
        raise SetupError('SQLite changed during capture; stop the old Bridge and retry.')
    return digest.hexdigest()


def inspect(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        if conn.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise SetupError('SQLite integrity check failed.')
        if conn.execute('PRAGMA foreign_key_check').fetchall():
            raise SetupError('SQLite foreign key check failed.')
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'alembic_version' in names:
            rows = conn.execute('SELECT version_num FROM alembic_version').fetchall()
            if len(rows) != 1 or rows[0][0] not in ('bridge_orm_0001', 'bridge_orm_0002', 'bridge_orm_0003'):
                raise SetupError('Unsupported ORM revision.')
            return 'orm', rows[0][0]
        if {'schema_migrations', 'system_config', 'devices', 'recipes', 'settings', 'session_state'} <= names:
            return 'legacy', None
        raise SetupError('Unrecognized SQLite schema.')


@record_import
def import_sqlite(state, source, *, _owned_capture=False):
    if state.value['status'] != 'in_progress':
        raise SetupError('Start an installation attempt first.')
    source = Path(source).expanduser()
    owned = (_owned_capture and source.parent.parent == state.staging()
             and source.parent.name.startswith('sqlite-source-'))
    if source.resolve().is_relative_to(state.root) and not owned:
        raise SetupError('Select a snapshot outside the new installation.')
    job = Path(tempfile.mkdtemp(prefix='sqlite-import-', dir=str(state.staging())))
    captured = job / 'captured.sqlite3'
    digest = capture(source, captured)
    kind, revision = inspect(captured)
    target = job / 'bridge.sqlite3'
    if kind == 'legacy':
        from storage.orm_normalize import normalize_copy
        normalize_copy(source=captured, destination=target)
    else:
        from alembic import command
        from alembic.config import Config
        from storage.repositories.orm import NormalizedRepository
        # Only the private capture is upgraded. Keep a separate captured backup.
        with closing(sqlite3.connect(captured)) as original:
            with closing(sqlite3.connect(target)) as dest:
                original.backup(dest)
        cfg = Config()
        cfg.set_main_option('script_location', str(Path(__file__).resolve().parents[1] / 'storage/alembic'))
        cfg.attributes['db_path'] = target
        command.upgrade(cfg, 'head')
        NormalizedRepository(target)
    inspect(target)
    # Inspect ORM headers and reconstruct entities without relaxing runtime validation.
    from storage.models import session_scope
    from storage.mappers import _config_from_orm
    from storage.repositories.orm import NormalizedRepository
    from config import BridgeConfig
    from recipe_engine.models import Recipe
    repo = NormalizedRepository(target)
    with session_scope(target, readonly=True) as session:
        config = _config_from_orm(session)
    parsed = BridgeConfig.from_dict(config)
    if config['devices']:
        parsed.validate()
        for row in repo.list_recipes():
            Recipe.from_dict(row['recipe']).validate(parsed)
    report = {'version': 1, 'status': 'imported_staging', 'source_kind': kind,
              'source_revision': revision, 'source_sha256': digest,
              'database': str(target.relative_to(state.staging())),
              'devices': len(config['devices']), 'recipes': len(repo.list_recipes()),
              'needs_review': not bool(config['devices']), 'runtime_authorized': False,
              'events': [event('imported', 'sqlite_validated')]}
    save_report(job, report)
    return report
