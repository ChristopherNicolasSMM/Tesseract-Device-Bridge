"""Single persistence boundary for the legacy and experimental ORM runtimes.

The old SQLite store is the default. The ORM backend is explicitly opt-in,
requires the independently normalized 0003 database and *always* forces
simulation, even if hardware settings saved in the database say 'real'.
No function writes simultaneously to both schemas.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path

from storage import sqlite_store as legacy
from storage.migrate import StorageError
from tesseract_bridge.infrastructure.env import flag


DEFAULT_CONTROL_SETTINGS = legacy.DEFAULT_CONTROL_SETTINGS
DEFAULT_DB = legacy.DEFAULT_DB
dumps = legacy.dumps
INITIAL_CONFIG = legacy.INITIAL_CONFIG


def storage_mode():
    mode = os.environ.get("TESSERACT_BRIDGE_STORAGE_MODE", "legacy").strip().lower()
    if mode not in ("legacy", "orm"):
        raise StorageError("TESSERACT_BRIDGE_STORAGE_MODE inválido: use legacy ou orm.")
    return mode


def db_path():
    return legacy.db_path()


def _orm():
    if storage_mode() != "orm":
        raise StorageError("Backend ORM não está selecionado.")
    if not flag("TESSERACT_BRIDGE_SIMULATION_ONLY", False):
        raise StorageError(
            "Backend ORM experimental exige SIMULATION_ONLY=1; "
            "é proibido acionar GPIO real nesta fase."
        )
    if not os.environ.get("TESSERACT_BRIDGE_DB"):
        raise StorageError("ORM exige caminho de banco explícito no .env.")
    from storage.repositories.write import OrmStore
    try:
        return OrmStore(db_path())
    except Exception as exc:
        # Fail closed; do not silently fall back to the legacy JSON tables.
        raise StorageError("Banco ORM 0003 não validado: " + str(exc)) from exc


def initialize(*, path=None, seed=True):
    if storage_mode() == "legacy":
        return legacy.initialize(path=path, seed=seed)
    if path is not None and Path(path).resolve() != db_path():
        raise StorageError("No modo ORM, configure o banco explicitamente no .env.")
    _orm()
    return db_path()


def connection(*, writable=False, path=None):
    if storage_mode() != "legacy":
        raise StorageError("SQL legado desativado no runtime ORM. Use repositórios.")
    return legacy.connection(writable=writable, path=path)


def backup(destination):
    if storage_mode() == "legacy":
        return legacy.backup(destination)
    _orm()
    source, target = db_path(), Path(destination).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise StorageError("Backup já existe: " + str(target))
    with closing(sqlite3.connect(str(source))) as src:
        with closing(sqlite3.connect(str(target))) as dest:
            src.backup(dest)
    target.chmod(0o600)
    return target


def _call(name, *args, **kwargs):
    if storage_mode() == "legacy":
        return getattr(legacy, name)(*args, **kwargs)
    return getattr(_orm(), name)(*args, **kwargs)


def load_config():
    return _call("load_config")


def config_revision():
    return _call("config_revision")


def apply_config(config, *, action="admin_apply", expected_revision=None):
    return _call("apply_config", config, action=action, expected_revision=expected_revision)


def save_draft(config):
    return _call("save_draft", config)


def list_drafts():
    return _call("list_drafts")


def load_draft(draft_id):
    return _call("load_draft", draft_id)


def activate_draft(draft_id):
    return _call("activate_draft", draft_id)


def list_recipe_rows():
    return _call("list_recipe_rows")


def recipe_row(recipe_id):
    return _call("recipe_row", recipe_id)


def create_recipe(recipe_id, source, payload):
    return _call("create_recipe", recipe_id, source, payload)


def update_recipe(recipe_id, payload):
    return _call("update_recipe", recipe_id, payload)


def delete_recipe(recipe_id):
    return _call("delete_recipe", recipe_id)


def replace_entities(source, entries):
    return _call("replace_entities", source, entries)


def get_active_recipe():
    return _call("get_active_recipe")


def set_active_recipe(recipe_id):
    return _call("set_active_recipe", recipe_id)


def load_factory_defaults():
    return _call("load_factory_defaults")


def load_control():
    return _call("load_control")


def save_control(payload):
    return _call("save_control", payload)


def load_calibrations():
    return _call("load_calibrations")


def save_calibrations(payload):
    return _call("save_calibrations", payload)


def load_session_state():
    return _call("load_session_state")


def save_session_state(payload):
    return _call("save_session_state", payload)


def audit_events(limit=100):
    return _call("audit_events", limit)
