"""Normalized ORM copy tests. Never access hardware or production databases."""
import json
import sqlite3

import pytest
from sqlalchemy import inspect

from storage import sqlite_store as store
from storage.orm_normalize import normalize_copy, _legacy_snapshot, _config_from_orm, NormalizationError
from storage.models import session_scope, Device, Recipe, ControlProfile


def test_copy_preserves_source_and_normalizes_all_known_entities(isolated_sqlite, tmp_path):
    from tests.test_data_store import config, recipe

    cfg = config()
    store.create_recipe("private:trial", "private", recipe("Trial"))
    settings = store.load_control()
    settings["boil_temperature"] = 96.3
    store.save_control(settings)
    original = isolated_sqlite.read_bytes()
    destination = tmp_path / "normalized.sqlite3"
    result = normalize_copy(source=isolated_sqlite, destination=destination)
    assert result["devices"] == 2
    assert result["recipes"] == 1
    assert result["control_profiles"] == 2
    assert isolated_sqlite.read_bytes() == original
    with session_scope(destination, readonly=True) as session:
        assert len(session.query(Device).all()) == 2
        assert session.get(Recipe, "private:trial").name == "Trial"
        assert session.get(ControlProfile, "control").boil_temperature == 96.3
        assert _config_from_orm(session)["backend"] == "simulated"
    with sqlite3.connect(str(destination)) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "bridge_orm_0001"


def test_copy_does_not_overwrite_existing_destination(isolated_sqlite, tmp_path):
    destination = tmp_path / "existing.sqlite3"
    destination.write_bytes(b"DO_NOT_TOUCH")
    with pytest.raises(NormalizationError, match="já existe"):
        normalize_copy(source=isolated_sqlite, destination=destination)
    assert destination.read_bytes() == b"DO_NOT_TOUCH"


def test_unknown_nested_hardware_fails_closed_without_touching_source(isolated_sqlite, tmp_path):
    cfg = store.load_config()
    cfg["devices"][0]["hardware"]["new_nested_feature"] = {"switch": "manual"}
    store.apply_config(cfg)
    destination = tmp_path / "bad.sqlite3"
    old = isolated_sqlite.read_bytes()
    with pytest.raises(NormalizationError, match="aninhada"):
        normalize_copy(source=isolated_sqlite, destination=destination)
    assert not destination.exists()
    assert isolated_sqlite.read_bytes() == old


def test_models_use_typed_columns_not_json():
    for model in (Device, Recipe, ControlProfile):
        columns = inspect(model).columns
        assert all("JSON" not in str(c.type).upper() for c in columns)
    assert "pin" in inspect(Device).columns
    assert "boil_temperature" in inspect(ControlProfile).columns
