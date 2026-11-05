"""Create an empty ORM database only inside the current installation attempt."""
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from .state import SetupError


def bootstrap_empty(state):
    if state.value['status'] != 'in_progress':
        raise SetupError('Start an installation attempt first.')
    target = state.staging() / 'bridge.sqlite3'
    if target.exists() or target.is_symlink():
        validate_empty(target)
        return target
    # Lazy imports keep storage out of the initial wizard bootstrap.
    from alembic import command
    from alembic.config import Config
    from config import MqttConfig, PanelConfig
    from storage.models import session_scope, BridgeSettings, MqttSettings, PanelSettings
    from storage.mappers import _control_to_orm
    from storage.sqlite_store import DEFAULT_CONTROL_SETTINGS
    fd = os.open(str(target), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        project = Path(__file__).resolve().parents[1]
        cfg = Config()
        cfg.set_main_option('script_location', str(project / 'storage/alembic'))
        cfg.attributes['db_path'] = target
        command.upgrade(cfg, 'head')
        m, p = MqttConfig(), PanelConfig()
        with session_scope(target) as session:
            session.add(BridgeSettings(id=1, backend='simulated', revision=1))
            session.add(MqttSettings(id=1, enabled=False, host=m.host, port=m.port,
                username=None, password=None, client_id=m.client_id,
                topic_prefix=m.topic_prefix, reconnect_interval_seconds=m.reconnect_interval_seconds))
            session.add(PanelSettings(id=1, enabled=True, host='127.0.0.1', port=p.port))
            for key in ('control', 'control_factory'):
                session.add(_control_to_orm(key, DEFAULT_CONTROL_SETTINGS, 1))
        validate_empty(target)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target


def validate_empty(target):
    if target.is_symlink():
        raise SetupError('Linked staging database rejected.')
    with closing(sqlite3.connect(target.as_uri() + '?mode=ro', uri=True)) as conn:
        if conn.execute('PRAGMA quick_check').fetchone()[0] != 'ok' or conn.execute('PRAGMA foreign_key_check').fetchall():
            raise SetupError('Invalid database integrity.')
        if conn.execute('SELECT version_num FROM alembic_version').fetchone()[0] != 'bridge_orm_0003':
            raise SetupError('Unexpected ORM revision.')
        for table in ('bridge_devices_v2', 'bridge_recipes_v2'):
            if conn.execute('SELECT count(*) FROM ' + table).fetchone()[0]:
                raise SetupError('Staging is not an empty installation.')
        if conn.execute('SELECT backend FROM bridge_settings_v2 WHERE id=1').fetchone() != ('simulated',):
            raise SetupError('Invalid bootstrap configuration.')
