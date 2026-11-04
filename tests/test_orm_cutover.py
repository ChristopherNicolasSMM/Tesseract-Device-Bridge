"""Experimental ORM simulation cutover; each test uses a disposable copy.

No test opens the real GPIO backend or writes to imported.sqlite3.
"""
import copy
import sqlite3
from dataclasses import asdict

import pytest

from config import BridgeConfig
from device_runtime import DeviceRuntime
from gpio.simulated_backend import SimulatedGPIOBackend
from panel.app import create_panel_app
from recipe_engine.state import RecipeState
from storage import sqlite_store as legacy
from storage import store_router as store
from storage.migrate import StorageError
from storage.models import RecipeRevision, session_scope
from storage.orm_normalize import normalize_copy
from storage.repositories.write import OrmStore


@pytest.fixture
def normalized(isolated_sqlite, tmp_path, monkeypatch):
    from tests.test_data_store import config
    config()  # add a heater to exercise recipes, GPIO still simulated
    source = isolated_sqlite
    before = source.read_bytes()
    candidate = tmp_path / "normalized-v3-test.sqlite3"
    normalize_copy(source=source, destination=candidate)
    monkeypatch.setenv("TESSERACT_BRIDGE_DB", str(candidate))
    monkeypatch.setenv("TESSERACT_BRIDGE_STORAGE_MODE", "orm")
    monkeypatch.setenv("TESSERACT_BRIDGE_SIMULATION_ONLY", "1")
    assert store.initialize() == candidate
    yield source, candidate, before
    assert source.read_bytes() == before


def test_cutover_mode_uses_typed_orm_only(normalized):
    source, candidate, _ = normalized
    cfg = store.load_config()
    assert len(cfg["devices"]) == 2
    assert store.storage_mode() == "orm"
    assert store.config_revision() == 2
    with sqlite3.connect(str(candidate)) as conn:
        old = conn.execute("SELECT count(*) FROM devices").fetchone()[0]
    change = copy.deepcopy(cfg)
    change["devices"][0]["name"] = "Sensor ORM"
    assert store.apply_config(change, expected_revision=2) == 3
    assert store.load_config()["devices"][0]["name"] == "Sensor ORM"
    with sqlite3.connect(str(candidate)) as conn:
        assert conn.execute("SELECT count(*) FROM devices").fetchone()[0] == old
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    with sqlite3.connect(str(source)) as conn:
        assert conn.execute("SELECT revision FROM system_config").fetchone()[0] == 2


def test_stale_revision_rejected_without_partial_change(normalized):
    current = store.load_config()
    current["devices"][0]["name"] = "Declined"
    with pytest.raises(StorageError, match="alterada"):
        store.apply_config(current, expected_revision=1)
    assert store.load_config()["devices"][0]["name"] != "Declined"


def test_draft_approval_updates_next_boot_not_current_runtime(normalized):
    config = BridgeConfig.from_dict(store.load_config())
    runtime = DeviceRuntime(config, SimulatedGPIOBackend())
    try:
        payload = copy.deepcopy(store.load_config())
        payload["devices"][0]["name"] = "Nome para próximo boot"
        draft = store.save_draft(payload)
        assert store.load_config()["devices"][0]["name"] != "Nome para próximo boot"
        assert store.activate_draft(draft) == 3
        assert store.load_config()["devices"][0]["name"] == "Nome para próximo boot"
        assert runtime.list_devices()[0].name != "Nome para próximo boot"
        assert store.list_drafts()[0]["status"] == "applied"
        with pytest.raises(StorageError, match="já aplicado"):
            store.activate_draft(draft)
    finally:
        runtime.shutdown()


def test_recipe_update_preserves_active_link_and_history(normalized):
    from tests.test_data_store import recipe
    rid = "private:original"
    store.create_recipe(rid, "private", recipe("Original"))
    store.set_active_recipe(rid)
    store.update_recipe(rid, recipe("Revisada"))
    assert store.get_active_recipe() == rid
    assert store.recipe_row(rid)["revision"] == 2
    assert len(store.list_recipe_rows()) == 1
    with session_scope(store.db_path(), readonly=True) as session:
        assert session.get(RecipeRevision, (rid, 1)) is not None
        assert session.get(RecipeRevision, (rid, 2)) is not None


def test_bulk_recipe_replacement_preserves_monotonic_revision(normalized):
    from tests.test_data_store import recipe
    entries = [{"id": "trial", "recipe": recipe("First")}]
    store.replace_entities("private", entries)
    assert store.recipe_row("private:trial")["revision"] == 1
    store.replace_entities("private", [{"id": "trial", "recipe": recipe("Updated")}])
    assert store.recipe_row("private:trial")["revision"] == 2


def test_control_calibration_and_session_write_relationally(normalized):
    settings = store.load_control()
    settings["boil_temperature"] = 96.2
    store.save_control(settings)
    assert store.load_control()["boil_temperature"] == 96.2
    assert store.load_factory_defaults()["boil_temperature"] == 100.0
    store.save_calibrations({"schema": 1, "sensors": {
        "demo_temperature": {"address": None, "offset_c": 0.75}
    }})
    assert store.load_calibrations()["sensors"]["demo_temperature"]["offset_c"] == 0.75
    state = asdict(RecipeState.fresh("Test"))
    state.update(status="paused_after_crash", control_settings=store.load_control())
    store.save_session_state(state)
    assert store.load_session_state() == state


def test_admin_http_uses_single_orm_backend(normalized, monkeypatch):
    monkeypatch.setenv("TESSERACT_BRIDGE_ADMIN_TOKEN", "sufficiently-long-test-admin-token")
    config = BridgeConfig.from_dict(store.load_config())
    runtime = DeviceRuntime(config, SimulatedGPIOBackend())
    try:
        http = create_panel_app(config, runtime).test_client()
        headers = {"X-Bridge-Admin-Token": "sufficiently-long-test-admin-token"}
        assert http.get("/api/admin/config").status_code == 401
        response = http.get("/api/admin/config", headers=headers)
        assert response.status_code == 200
        payload = response.json["config"]
        payload["devices"][0]["name"] = "HTTP ORM"
        posted = http.post("/api/admin/drafts", headers=headers, json=payload)
        assert posted.status_code == 201, posted.json
        approved = http.post(
            "/api/admin/drafts/" + str(posted.json["id"]) + "/activate",
            headers=headers,
        )
        assert approved.status_code == 200, approved.json
        assert store.load_config()["devices"][0]["name"] == "HTTP ORM"
        assert http.get("/api/admin/audit", headers=headers).status_code == 200
    finally:
        runtime.shutdown()


def test_orm_refuses_hardware_mode(normalized, monkeypatch):
    monkeypatch.setenv("TESSERACT_BRIDGE_SIMULATION_ONLY", "0")
    with pytest.raises(StorageError, match="SIMULATION_ONLY"):
        store.load_config()


def test_orm_disallows_raw_legacy_sql_and_backup_is_valid(normalized, tmp_path):
    with pytest.raises(StorageError, match="SQL legado"):
        store.connection()
    backup = tmp_path / "orm-backup.sqlite3"
    assert store.backup(backup) == backup
    with sqlite3.connect(str(backup)) as conn:
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "bridge_orm_0003"


def test_default_legacy_backend_still_operates(isolated_sqlite):
    assert store.storage_mode() == "legacy"
    assert store.load_config() == legacy.load_config()


def test_orm_rejects_unmigrated_db(isolated_sqlite, monkeypatch):
    monkeypatch.setenv("TESSERACT_BRIDGE_STORAGE_MODE", "orm")
    monkeypatch.setenv("TESSERACT_BRIDGE_SIMULATION_ONLY", "1")
    with pytest.raises(StorageError, match="não validado"):
        store.load_config()


def test_recipe_state_persistence_follows_selected_backend(normalized):
    from recipe_engine.state import RecipeState
    current = RecipeState.fresh("Persistência ORM")
    current.status = "paused_after_crash"
    current.save(None)
    loaded = RecipeState.load(None)
    assert loaded.recipe_name == "Persistência ORM"
    assert loaded.status == "paused_after_crash"



def test_runtime_config_is_simulated_even_in_orm_mode(normalized):
    from storage.launch_config import load_runtime_config
    config = load_runtime_config()
    assert config.backend == "simulated"
    assert config.mqtt.enabled is False
    assert config.panel.host == "127.0.0.1"


def test_control_snapshot_does_not_change_with_next_recipe_profile(normalized):
    from recipe_engine.state import RecipeState
    state = asdict(RecipeState.fresh("Snapshot"))
    state["control_settings"] = store.load_control()
    state["status"] = "paused_after_crash"
    store.save_session_state(state)
    original = store.load_session_state()["control_settings"]["boil_temperature"]
    updated = store.load_control()
    updated["boil_temperature"] = 93.7
    store.save_control(updated)
    assert store.load_control()["boil_temperature"] == 93.7
    assert store.load_session_state()["control_settings"]["boil_temperature"] == original


def test_high_level_recipe_service_uses_orm(normalized):
    import data
    from tests.test_data_store import recipe
    cfg = BridgeConfig.from_dict(store.load_config())
    name = data.create_recipe("private", recipe("API Alta Camada"), cfg)
    assert data.get_recipe_dict_by_id(name)["name"] == "API Alta Camada"
    data.set_active_recipe_id(name)
    data.update_recipe(name, recipe("Receita Editada"), cfg)
    assert data.get_active_recipe_id() == name
    assert data.load_active_recipe(cfg).name == "Receita Editada"


def test_recipe_update_has_no_identity_conflict_warnings(normalized):
    import warnings
    from sqlalchemy.exc import SAWarning
    from tests.test_data_store import recipe
    store.create_recipe("private:stable", "private", recipe("Before"))
    store.set_active_recipe("private:stable")
    with warnings.catch_warnings():
        warnings.simplefilter("error", SAWarning)
        store.update_recipe("private:stable", recipe("After"))
        store.replace_entities("private", [{
            "id": "stable", "recipe": recipe("After again")
        }])
    assert store.recipe_row("private:stable")["revision"] == 3
    assert store.get_active_recipe() == "private:stable"
