"""SQLite storage regression tests, replacing old file-system mutation tests."""
import json
import sqlite3

import pytest

import data
from config import BridgeConfig
from recipe_engine.models import RecipeError
from storage import sqlite_store as store
from storage.migrate import StorageError


def config():
    raw = store.load_config()
    raw["devices"] += [{
        "id": "heater", "name": "Aquecedor", "role": "actuator", "subtype": "digital",
        "command_topic": "actuators/heater/set", "hardware": {"pin": 17, "window_seconds": 5},
        "is_risk": True, "failsafe_value": False,
    }]
    store.apply_config(raw)
    return BridgeConfig.from_dict(raw)


def recipe(name="Pilsen"):
    return {
        "name": name,
        "vessels": [{"id": "mash", "name": "Mostura",
                     "sensor_device_id": "demo_temperature", "heater_device_id": "heater",
                     "pid": {"kp": 2, "ki": 0.1, "kd": 0}}],
        "steps": [{"vessel": "mash", "target_temp": 67, "hold_minutes": 45}],
    }


def test_blank_install_is_simulated():
    assert store.load_config()["backend"] == "simulated"
    assert len(store.load_config()["devices"]) == 1
    assert data.list_recipes() == []


def test_recipe_round_trip_revision_and_visibility():
    cfg = config()
    rid = data.create_recipe("private", recipe(), cfg)
    assert rid == "private:pilsen"
    assert data.get_recipe_dict_by_id(rid) == recipe()
    assert data.list_recipes(cfg)[0]["editable"]
    assert data.get_effective_active_recipe_id() is None
    data.set_active_recipe_id(rid)
    assert data.get_effective_active_recipe_id() == rid
    data.update_recipe(rid, recipe("Pilsen revisada"), cfg)
    assert store.recipe_row(rid)["revision"] == 2
    assert data.load_active_recipe(cfg).name == "Pilsen revisada"
    data.delete_recipe(rid)
    assert data.get_active_recipe_id() is None


def test_base_recipe_remains_protected():
    cfg = config()
    store.create_recipe("public:base", "public", recipe())
    with store.connection(writable=True) as conn:
        conn.execute("UPDATE recipes SET editable=0 WHERE id='public:base'")
    with pytest.raises(RecipeError):
        data.update_recipe("public:base", recipe("Edited"), cfg)
    with pytest.raises(RecipeError):
        data.delete_recipe("public:base")


def test_slug_collisions_are_handled():
    cfg = config()
    assert data.create_recipe("public", recipe("IPA"), cfg) == "public:ipa"
    assert data.create_recipe("public", recipe("IPA"), cfg) == "public:ipa-2"


def test_invalid_recipe_never_writes():
    cfg = config()
    invalid = recipe()
    invalid["vessels"][0]["heater_device_id"] = "missing"
    with pytest.raises(RecipeError):
        data.create_recipe("private", invalid, cfg)
    assert data.list_recipes() == []


def test_duplicate_pin_fails_draft_without_mutating_active_revision():
    payload = store.load_config()
    payload["devices"].append({
        "id": "other", "name": "Other", "role": "sensor", "subtype": "temperature",
        "state_topic": "sensors/other/state", "hardware": {"pin": 4},
    })
    before = store.config_revision()
    with pytest.raises(Exception):
        store.save_draft(payload)
    assert store.config_revision() == before


def test_valid_draft_is_applied_only_on_explicit_approval():
    before = store.load_config()
    revision = store.config_revision()
    pending = json.loads(json.dumps(before))
    pending["devices"][0]["name"] = "Novo nome"
    draft = store.save_draft(pending)
    assert store.load_config() == before
    assert store.activate_draft(draft) == revision + 1
    assert store.load_config()["devices"][0]["name"] == "Novo nome"


def test_control_and_calibration_store_round_trip():
    settings=store.load_control()
    settings["boil_temperature"] = 98.5
    store.save_control(settings)
    assert store.load_control()["boil_temperature"] == 98.5
    calibrations={"schema": 1, "sensors": {"demo_temperature": {
        "address": None, "offset_c": 2.1}}}
    store.save_calibrations(calibrations)
    assert store.load_calibrations() == calibrations


def test_session_state_is_atomic_json():
    payload={"status": "paused_after_crash", "recipe_name": "Pilsen"}
    store.save_session_state(payload)
    assert store.load_session_state() == payload


def test_schema_migrations_are_idempotent_and_integrity_checked(isolated_sqlite):
    old_revision=store.config_revision()
    store.initialize()
    assert store.config_revision() == old_revision
    with store.connection() as conn:
        assert conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] >= 2


def test_new_sqlite_file_is_not_plain_json(isolated_sqlite):
    assert isolated_sqlite.read_bytes()[:16] == b"SQLite format 3\x00"
