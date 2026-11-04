"""Real legacy import fixtures; source must remain byte-for-byte untouched."""
import json
from pathlib import Path

import pytest
import yaml

from storage import sqlite_store as store
from storage.legacy_import import collect, archive_source, import_snapshot, LegacyImportError


@pytest.fixture
def legacy_source(tmp_path):
    root = tmp_path / "old_install"
    (root / "data/public").mkdir(parents=True)
    (root / "data/private").mkdir(parents=True)
    config = store.load_config()
    config["devices"][0]["hardware"].update(driver="ds18b20", address="28-000000000001")
    config["devices"].append({
        "id": "heater", "name": "Resistência", "role": "actuator", "subtype": "digital",
        "command_topic": "actuators/heater/set", "hardware": {"pin": 17, "window_seconds": 5},
        "is_risk": True, "failsafe_value": False
    })
    (root / "data/public/devices.yml").write_text(yaml.safe_dump(config), encoding="utf-8")
    recipe = {
        "name": "Legacy pilsen",
        "vessels": [{
            "id": "mash", "name": "Mostura", "heater_device_id": "heater",
            "sensor_device_id": "demo_temperature", "pid": {"kp": 2, "ki": 0.1, "kd": 0}
        }],
        "steps": [{"vessel": "mash", "target_temp": 65, "hold_minutes": 60}]
    }
    (root / "data/public/receita_base.yaml").write_text(yaml.safe_dump(recipe), encoding="utf-8")
    private = [{"id": "meu-lote", "recipe": dict(recipe, name="Meu lote privado")}]
    (root / "data/private/receita.json").write_text(json.dumps(private), encoding="utf-8")
    (root / "data/active_recipe.txt").write_text("private:meu-lote", encoding="utf-8")
    cal={"schema": 1, "sensors": {"demo_temperature":{
        "address": "28-000000000001", "offset_c": 2.1
    }}}
    (root / "data/private/sensor_calibration.json").write_text(json.dumps(cal), encoding="utf-8")
    (root / "data/private/recipe_state.json").write_text(
        json.dumps({"recipe_name": "Legacy pilsen", "status": "ramping", "step_index": 0}), encoding="utf-8")
    return root


def test_migration_preserves_all_documents_in_one_transaction(legacy_source, tmp_path):
    snapshot = collect(legacy_source)
    assert snapshot["counts"] == {"devices": 2, "recipes": 2, "calibrations": 1, "session_state": 1}
    before = {rel: (legacy_source / rel).read_bytes() for rel in snapshot["file_hashes"]}
    archive = archive_source(snapshot, tmp_path / "backup")
    assert archive.is_file()
    destination = tmp_path / "fresh" / "migrated.sqlite3"
    import_snapshot(snapshot, destination=destination)
    assert destination.is_file()
    with store.connection(path=destination) as conn:
        assert conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0] == 2
        active = conn.execute("SELECT recipe_id FROM active_recipe WHERE id=1").fetchone()[0]
        assert active == "private:meu-lote"
        state = json.loads(conn.execute("SELECT state_json FROM session_state WHERE id=1").fetchone()[0])
        assert state["status"] == "paused_after_crash"
        calibration = conn.execute("SELECT offset_c,address FROM sensor_calibrations").fetchone()
        assert calibration[0] == pytest.approx(2.1)
        assert calibration[1] == "28-000000000001"
    after = {rel: (legacy_source / rel).read_bytes() for rel in snapshot["file_hashes"]}
    assert before == after


def test_reimport_is_rejected_without_touching_existing_db(legacy_source,tmp_path):
    snap=collect(legacy_source)
    target=tmp_path/"fresh.sqlite3"
    import_snapshot(snap, destination=target)
    original=target.read_bytes()
    with pytest.raises(LegacyImportError,match="já existe"):
        import_snapshot(snap,destination=target)
    assert target.read_bytes() == original


def test_invalid_legacy_config_is_rejected_before_creating_db(legacy_source,tmp_path):
    file=legacy_source/"data/public/devices.yml"
    file.write_text("backend: real\nmqtt: {}\npanel: {}\ndevices: []\n",encoding="utf-8")
    with pytest.raises(Exception):
        collect(legacy_source)
    assert not (tmp_path/"never.sqlite3").exists()


def test_importer_detects_stale_rom_calibration(legacy_source):
    path=legacy_source/"data/private/sensor_calibration.json"
    path.write_text(json.dumps({"schema":1,"sensors":{
        "demo_temperature":{"address":"28-not-this-device","offset_c":2.1}}}),encoding="utf-8")
    with pytest.raises(ValueError,match="recalibre"):
        collect(legacy_source)



def test_legacy_remote_without_state_topic_rejected_by_default(legacy_source):
    """The importer must never silently enable remote actuator commands."""
    path = legacy_source / "data/public/devices.yml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["devices"].append({
        "id": "pump_b1", "name": "Bomba 1", "role": "actuator",
        "subtype": "digital", "command_topic": "actuators/pump_b1/set",
        "hardware": {"pin": 19, "remote_control": True},
        "is_risk": True, "failsafe_value": False,
    })
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(LegacyImportError, match="pump_b1"):
        collect(legacy_source)


def test_explicit_remote_downgrade_keeps_backup_original_and_sqlite_safe(legacy_source, tmp_path):
    """An explicit downgrade is private to the SQLite import, fully auditable."""
    import zipfile

    path = legacy_source / "data/public/devices.yml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["devices"].append({
        "id": "pump_b1", "name": "Bomba 1", "role": "actuator",
        "subtype": "digital", "command_topic": "actuators/pump_b1/set",
        "hardware": {"pin": 19, "remote_control": True},
        "is_risk": True, "failsafe_value": False,
    })
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    original = path.read_bytes()
    snapshot = collect(legacy_source, disable_invalid_remote_control=True)
    assert snapshot["counts"]["devices"] == 3
    assert snapshot["repairs"] == [{
        "device_id": "pump_b1", "field": "hardware.remote_control",
        "source_value": True, "imported_value": False,
        "reason": "missing_state_topic",
    }]
    imported = next(d for d in snapshot["config"]["devices"] if d["id"] == "pump_b1")
    assert imported["hardware"]["remote_control"] is False
    assert path.read_bytes() == original
    archive = archive_source(snapshot, tmp_path / "backup")
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.read("data/public/devices.yml") == original
    destination = tmp_path / "migrated.sqlite3"
    import_snapshot(snapshot, destination=destination)
    with store.connection(path=destination) as conn:
        row = conn.execute(
            "SELECT config_json FROM devices WHERE id='pump_b1'"
        ).fetchone()
        assert json.loads(row[0])["hardware"]["remote_control"] is False
        manifest = json.loads(conn.execute(
            "SELECT manifest_json FROM legacy_imports"
        ).fetchone()[0])
        assert manifest["repairs"] == snapshot["repairs"]
    assert path.read_bytes() == original


def test_explicit_remote_downgrade_does_not_bypass_other_safety_validation(legacy_source):
    path = legacy_source / "data/public/devices.yml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["devices"].append({
        "id": "gas", "name": "Fonte de gás", "role": "actuator",
        "subtype": "digital", "command_topic": "actuators/gas/set",
        "hardware": {"pin": 19, "remote_control": True,
                     "heating_source": {"participation": "auxiliary"}},
        "is_risk": True, "failsafe_value": False,
    })
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(LegacyImportError):
        collect(legacy_source, disable_invalid_remote_control=True)
