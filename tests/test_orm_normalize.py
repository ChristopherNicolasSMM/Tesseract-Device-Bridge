"""Normalized ORM copy tests. Never access hardware or production databases."""
import json
import sqlite3

import pytest
from sqlalchemy import inspect

from storage import sqlite_store as store
from storage.orm_normalize import normalize_copy, validate_source, _config_from_orm, NormalizationError
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
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "bridge_orm_0003"


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


def test_readonly_preflight_reports_unmapped_nested_hardware_before_any_copy(isolated_sqlite, tmp_path):
    cfg = store.load_config()
    cfg["devices"][0]["hardware"]["unsupported_complex"] = {"outer": {"inner": 1}}
    store.apply_config(cfg)
    before = isolated_sqlite.read_bytes()
    with pytest.raises(NormalizationError, match="aninhada"):
        validate_source(isolated_sqlite)
    assert isolated_sqlite.read_bytes() == before
    assert not (tmp_path / "normalized.sqlite3").exists()


def test_failed_backfill_never_publishes_candidate(isolated_sqlite, tmp_path, monkeypatch):
    """Even a database/SQLAlchemy failure must not publish partial migrations."""
    from storage import orm_normalize
    destination = tmp_path / "candidate-not-created.sqlite3"
    original = isolated_sqlite.read_bytes()

    def broken_backfill(*_args):
        raise RuntimeError("falha intencional na gravação relacional")

    monkeypatch.setattr(orm_normalize, "_backfill", broken_backfill)
    with pytest.raises(RuntimeError, match="falha intencional"):
        normalize_copy(source=isolated_sqlite, destination=destination)
    assert not destination.exists()
    assert isolated_sqlite.read_bytes() == original


def test_referenced_active_recipe_preserves_foreign_keys(isolated_sqlite, tmp_path):
    """The active recipe FK must stay ON, and refer to a persisted Recipe."""
    from tests.test_data_store import config, recipe
    import sqlite3
    config()
    store.create_recipe("private:fk-test", "private", recipe("FK Test"))
    store.set_active_recipe("private:fk-test")
    destination = tmp_path / "with-active-recipe.sqlite3"
    normalize_copy(source=isolated_sqlite, destination=destination)
    with sqlite3.connect(str(destination)) as db:
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute(
            "SELECT recipe_id FROM bridge_active_recipe_v2 WHERE id=1"
        ).fetchone()[0] == "private:fk-test"
