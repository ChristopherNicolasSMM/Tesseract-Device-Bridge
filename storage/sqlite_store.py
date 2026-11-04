"""SQLite persistence: single on-device source of truth; no legacy file reads.

Each call uses its own short-lived connection. Runtime snapshots remain in
memory, so polling temperature and writing GPIO never touch this database.
"""
from __future__ import annotations

import contextlib
import json
import os
import sqlite3
from pathlib import Path

from storage.migrate import apply_migrations, check_schema, StorageError
from project_paths import DATA_DIR

DEFAULT_DB = DATA_DIR / "private" / "bridge.sqlite3"

DEFAULT_CONTROL_SETTINGS = {
    "mash_curve": [[-3, 100], [-2, 75], [-1, 60], [0, 50], [0.5, 30], [1, 0]],
    "alert_above": 3.0, "alert_clear": 2.5,
    "freeze_hold_on_alert": False,
    "boil_temperature": 100.0, "boil_power": 100.0,
    "vessel_profiles": {"mash": "mash", "boil": "boil"},
}
# Installations with no imported configuration stay simulated and cannot
# actuate real GPIOs. An administrator must approve a real configuration.
INITIAL_CONFIG = {
    "mqtt": {"enabled": False},
    "backend": "simulated",
    "panel": {"enabled": True, "host": "127.0.0.1", "port": 8088},
    "devices": [
        {"id": "demo_temperature", "name": "Temperatura (simulação)",
         "role": "sensor", "subtype": "temperature", "unit": "°C",
         "state_topic": "sensors/demo_temperature/state",
         "hardware": {"pin": 4},
         "simulated": {"initial_value": 25, "min": 0, "max": 120}},
    ],
}


def db_path():
    return Path(os.environ.get("TESSERACT_BRIDGE_DB", str(DEFAULT_DB))).expanduser().resolve()


def dumps(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


@contextlib.contextmanager
def connection(*, writable=False, path=None):
    path = Path(path) if path is not None else db_path()
    if not path.is_file():
        raise StorageError(f"Banco SQLite não encontrado: {path}. Execute 'python -m storage.cli init' ou importe os dados legados.")
    conn = sqlite3.connect(str(path), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute("PRAGMA synchronous=FULL")
    try:
        check_schema(conn)
        if writable:
            conn.execute("BEGIN IMMEDIATE")
        yield conn
        if writable:
            conn.commit()
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


def initialize(*, path=None, seed=True):
    target = Path(path) if path is not None else db_path()
    apply_migrations(target)
    if seed:
        with connection(writable=True, path=target) as conn:
            if conn.execute("SELECT 1 FROM system_config WHERE id=1").fetchone() is None:
                _write_config(conn, INITIAL_CONFIG, action="safe_initial_seed")
            conn.execute(
                "INSERT OR IGNORE INTO settings(key,value_json) VALUES('control',?)",
                (dumps(DEFAULT_CONTROL_SETTINGS),)
            )
            conn.execute(
                "INSERT OR IGNORE INTO settings(key,value_json) VALUES('control_factory',?)",
                (dumps(DEFAULT_CONTROL_SETTINGS),)
            )
    return target


def _read_config(conn):
    row = conn.execute("SELECT config_json, revision FROM system_config WHERE id=1").fetchone()
    if row is None:
        raise StorageError("Nenhuma configuração operacional no SQLite. Execute a importação ou inicialização.")
    value = json.loads(row["config_json"])
    value["devices"] = [json.loads(r["config_json"]) for r in
                        conn.execute("SELECT config_json FROM devices ORDER BY position")]
    return value, row["revision"]


def load_config():
    with connection() as conn:
        return _read_config(conn)[0]


def config_revision():
    with connection() as conn:
        return _read_config(conn)[1]


def _write_config(conn, config, *, action):
    # Call only after BridgeConfig.validate(); commit snapshots atomically.
    row = conn.execute("SELECT revision FROM system_config WHERE id=1").fetchone()
    revision = (row[0] + 1) if row else 1
    header = {key: config[key] for key in ("mqtt", "backend", "panel")}
    conn.execute(
        "INSERT INTO system_config(id,config_json,revision) VALUES(1,?,?) "
        "ON CONFLICT(id) DO UPDATE SET config_json=excluded.config_json,"
        "revision=excluded.revision,updated_at=CURRENT_TIMESTAMP",
        (dumps(header), revision)
    )
    conn.execute("DELETE FROM devices")
    for index, device in enumerate(config["devices"]):
        conn.execute("INSERT INTO devices(id,position,config_json) VALUES(?,?,?)",
                     (device["id"], index, dumps(device)))
    conn.execute("INSERT INTO configuration_revisions(revision,snapshot_json,action) VALUES(?,?,?)",
                 (revision, dumps(config), action))
    conn.execute("INSERT INTO audit_events(event_type,details_json) VALUES(?,?)",
                 ("config_revision", dumps({"revision": revision, "action": action})))
    return revision


def apply_config(config, *, action="admin_apply", expected_revision=None):
    from config import BridgeConfig
    parsed = BridgeConfig.from_dict(config)
    parsed.validate()
    with connection(writable=True) as conn:
        current = conn.execute("SELECT revision FROM system_config WHERE id=1").fetchone()
        if expected_revision is not None and (current is None or current[0] != expected_revision):
            raise StorageError("Configuração alterada por outro operador; recarregue a versão atual.")
        # A physical sensor replacement invalidates its old calibration.
        for device in parsed.devices:
            row = conn.execute("SELECT address FROM sensor_calibrations WHERE sensor_id=?",
                               (device.id,)).fetchone()
            if row and row[0] != device.hardware.get("address"):
                raise StorageError(f"Sensor {device.id} mudou ROM ID. Retire/recalibre o offset antes de aplicar.")
        return _write_config(conn, config, action=action)


def save_draft(config):
    from config import BridgeConfig
    parsed = BridgeConfig.from_dict(config)
    parsed.validate()
    with connection(writable=True) as conn:
        _, revision = _read_config(conn)
        cur = conn.execute(
            "INSERT INTO configuration_drafts(payload_json,base_revision) VALUES(?,?)",
            (dumps(config), revision)
        )
        return cur.lastrowid


def list_drafts():
    with connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id,base_revision,status,created_at FROM configuration_drafts ORDER BY id DESC LIMIT 30"
        )]


def activate_draft(draft_id):
    from config import BridgeConfig
    with connection(writable=True) as conn:
        row = conn.execute("SELECT payload_json,base_revision,status FROM configuration_drafts WHERE id=?",
                           (draft_id,)).fetchone()
        if row is None or row["status"] != "draft":
            raise StorageError("Rascunho não encontrado ou já aplicado.")
        config = json.loads(row["payload_json"])
        BridgeConfig.from_dict(config).validate()
        _, current_revision = _read_config(conn)
        if current_revision != row["base_revision"]:
            raise StorageError("Configuração ativa mudou desde a criação do rascunho; revise novamente.")
        for device in config["devices"]:
            stored = conn.execute("SELECT address FROM sensor_calibrations WHERE sensor_id=?",
                                  (device["id"],)).fetchone()
            if stored and stored[0] != device.get("hardware", {}).get("address"):
                raise StorageError("Calibração incompatível com novo endereço de " + device["id"])
        revision = _write_config(conn, config, action="approve_draft")
        conn.execute("UPDATE configuration_drafts SET status='applied' WHERE id=?", (draft_id,))
        return revision


def list_recipe_rows():
    with connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id,source,editable,recipe_json,revision FROM recipes ORDER BY source,id"
        )]


def recipe_row(recipe_id):
    with connection() as conn:
        row = conn.execute(
            "SELECT id,source,editable,recipe_json,revision FROM recipes WHERE id=?", (recipe_id,)
        ).fetchone()
        return dict(row) if row else None


def create_recipe(recipe_id, source, recipe):
    with connection(writable=True) as conn:
        conn.execute(
            "INSERT INTO recipes(id,source,editable,recipe_json) VALUES(?,?,1,?)",
            (recipe_id, source, dumps(recipe))
        )
        conn.execute(
            "INSERT INTO recipe_revisions(recipe_id,revision,recipe_json) VALUES(?,?,?)",
            (recipe_id, 1, dumps(recipe))
        )
        conn.execute("INSERT INTO audit_events(event_type,entity_id,details_json) VALUES('recipe_create',?,?)",
                     (recipe_id, "{}"))


def update_recipe(recipe_id, recipe):
    with connection(writable=True) as conn:
        row = conn.execute("SELECT editable,revision FROM recipes WHERE id=?", (recipe_id,)).fetchone()
        if row is None:
            raise StorageError("Receita não encontrada: " + recipe_id)
        if row["editable"] == 0:
            raise StorageError("Receita-base protegida; duplique-a para editar.")
        revision = row["revision"] + 1
        conn.execute("UPDATE recipes SET recipe_json=?,revision=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (dumps(recipe), revision, recipe_id))
        conn.execute("INSERT INTO recipe_revisions(recipe_id,revision,recipe_json) VALUES(?,?,?)",
                     (recipe_id, revision, dumps(recipe)))


def delete_recipe(recipe_id):
    with connection(writable=True) as conn:
        row = conn.execute("SELECT editable FROM recipes WHERE id=?", (recipe_id,)).fetchone()
        if row is None:
            raise StorageError("Receita não encontrada: " + recipe_id)
        if row["editable"] == 0:
            raise StorageError("Receita-base protegida.")
        conn.execute("DELETE FROM recipes WHERE id=?", (recipe_id,))


def get_active_recipe():
    with connection() as conn:
        row = conn.execute("SELECT recipe_id FROM active_recipe WHERE id=1").fetchone()
        return row[0] if row else None


def set_active_recipe(recipe_id):
    with connection(writable=True) as conn:
        if conn.execute("SELECT 1 FROM recipes WHERE id=?", (recipe_id,)).fetchone() is None:
            raise StorageError("Receita não encontrada: " + recipe_id)
        conn.execute(
            "INSERT INTO active_recipe(id,recipe_id) VALUES(1,?) "
            "ON CONFLICT(id) DO UPDATE SET recipe_id=excluded.recipe_id",
            (recipe_id,)
        )


def load_factory_defaults():
    with connection() as conn:
        row = conn.execute("SELECT value_json FROM settings WHERE key='control_factory'").fetchone()
        if row is None:
            raise StorageError("Padrões de fábrica não inicializados no SQLite.")
        return json.loads(row[0])


def load_control():
    with connection() as conn:
        row = conn.execute("SELECT value_json FROM settings WHERE key='control'").fetchone()
        if row is None:
            raise StorageError("Parâmetros de controle não inicializados.")
        return json.loads(row[0])


def save_control(value):
    with connection(writable=True) as conn:
        conn.execute(
            "INSERT INTO settings(key,value_json) VALUES('control',?) "
            "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,"
            "revision=settings.revision+1,updated_at=CURRENT_TIMESTAMP",
            (dumps(value),)
        )


def load_calibrations():
    with connection() as conn:
        return {"schema": 1, "sensors": {
            r["sensor_id"]: {"address": r["address"], "offset_c": r["offset_c"]}
            for r in conn.execute(
                "SELECT sensor_id,address,offset_c FROM sensor_calibrations ORDER BY sensor_id"
            )
        }}


def save_calibrations(payload):
    with connection(writable=True) as conn:
        conn.execute("DELETE FROM sensor_calibrations")
        for sensor_id, entry in payload["sensors"].items():
            conn.execute(
                "INSERT INTO sensor_calibrations(sensor_id,address,offset_c) VALUES(?,?,?)",
                (sensor_id, entry["address"], entry["offset_c"])
            )


def load_session_state():
    with connection() as conn:
        row = conn.execute("SELECT state_json FROM session_state WHERE id=1").fetchone()
        return json.loads(row[0]) if row else None


def save_session_state(value):
    with connection(writable=True) as conn:
        conn.execute(
            "INSERT INTO session_state(id,state_json) VALUES(1,?) "
            "ON CONFLICT(id) DO UPDATE SET state_json=excluded.state_json,"
            "updated_at=CURRENT_TIMESTAMP",
            (dumps(value),)
        )


def backup(destination):
    source = db_path()
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise StorageError("Backup já existe; escolha um arquivo novo: " + str(target))
    with connection() as conn:
        out = sqlite3.connect(str(target))
        try:
            conn.backup(out)
        finally:
            out.close()
    target.chmod(0o600)
    return target
