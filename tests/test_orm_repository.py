"""SQLAlchemy repository + migration-copy audit regressions."""
import json
import sqlite3

import pytest

from storage import sqlite_store as store
from storage.orm_normalize import normalize_copy, NormalizationError
from storage.orm_audit import audit_copy
from storage.repositories.orm import NormalizedRepository, RepositoryError


def _candidate(isolated_sqlite, tmp_path):
    from tests.test_data_store import config, recipe
    config()
    store.create_recipe("private:trial", "private", recipe("Trial"))
    store.save_session_state({"status": "paused_after_crash", "recipe_name": "Trial"})
    destination = tmp_path / "normalized.sqlite3"
    normalize_copy(source=isolated_sqlite, destination=destination)
    return destination


def test_repository_reads_all_normalized_domains(isolated_sqlite, tmp_path):
    candidate = _candidate(isolated_sqlite, tmp_path)
    repo = NormalizedRepository(candidate)
    assert len(repo.configuration()["devices"]) == 2
    assert repo.configuration_revision() == 2
    assert repo.recipe("private:trial")["recipe"]["name"] == "Trial"
    assert len(repo.list_recipes()) == 1
    assert repo.control_profile("control")["boil_temperature"] == 100.0
    assert repo.control_profile("control_factory")["boil_temperature"] == 100.0
    assert repo.active_recipe() is None
    assert repo.calibrations()["sensors"] == {}
    assert repo.session_state() == {
        "status": "paused_after_crash", "recipe_name": "Trial"
    }
    assert audit_copy(source=isolated_sqlite, candidate=candidate)["result"] == "OK"


def test_repository_rejects_legacy_only_db(isolated_sqlite):
    with pytest.raises(RepositoryError, match="sem tabelas ORM"):
        NormalizedRepository(isolated_sqlite)


def test_audit_detects_modified_session_state(isolated_sqlite, tmp_path):
    candidate = _candidate(isolated_sqlite, tmp_path)
    with sqlite3.connect(str(candidate)) as db:
        db.execute("UPDATE session_state SET state_json=? WHERE id=1",
                   (json.dumps({"status": "ramping"}),))
    with pytest.raises(NormalizationError, match="session_state"):
        audit_copy(source=isolated_sqlite, candidate=candidate)


def test_typed_control_update_on_candidate_only(isolated_sqlite, tmp_path):
    candidate = _candidate(isolated_sqlite, tmp_path)
    repo = NormalizedRepository(candidate)
    saved_revision = repo.control_revision()
    update = repo.control_profile()
    update["boil_temperature"] = 97.0
    assert repo.save_control_profile(update, expected_revision=saved_revision) == saved_revision + 1
    assert repo.control_profile()["boil_temperature"] == 97.0
    assert store.load_control()["boil_temperature"] == 100.0
    with pytest.raises(RepositoryError, match="Revisão alterada"):
        repo.save_control_profile(update, expected_revision=saved_revision)
    with pytest.raises(NormalizationError, match="controle"):
        audit_copy(source=isolated_sqlite, candidate=candidate)


def test_audit_rejects_same_file(isolated_sqlite):
    with pytest.raises(NormalizationError, match="diferentes"):
        audit_copy(source=isolated_sqlite, candidate=isolated_sqlite)



def test_explicit_orm_repository_uses_its_own_factory_when_global_backend_is_other_db(
    isolated_sqlite, tmp_path, monkeypatch
):
    """Independent repo updates never resolve defaults through store_router."""
    from storage.repositories.write import OrmStore
    candidate = _candidate(isolated_sqlite, tmp_path)
    monkeypatch.setenv("TESSERACT_BRIDGE_STORAGE_MODE", "orm")
    monkeypatch.setenv("TESSERACT_BRIDGE_SIMULATION_ONLY", "1")
    # Deliberately point the process-wide router to legacy-only SQLite:
    # this used to produce 'no such table: bridge_settings_v2'.
    monkeypatch.setenv("TESSERACT_BRIDGE_DB", str(isolated_sqlite))
    repo = NormalizedRepository(candidate)
    value = repo.control_profile()
    value["boil_temperature"] = 96.5
    old_revision = repo.control_revision()
    assert repo.save_control_profile(
        value, expected_revision=old_revision
    ) == old_revision + 1
    assert repo.control_profile()["boil_temperature"] == 96.5
    # The runtime's newer write service must obey the same rule.
    store_orm = OrmStore(candidate)
    another = store_orm.load_control()
    another["boil_temperature"] = 94.0
    store_orm.save_control(another)
    assert store_orm.load_control()["boil_temperature"] == 94.0
    # The original database and the candidate's factory profile remain intact.
    assert store.load_control()["boil_temperature"] == 100.0
    assert repo.control_profile("control_factory")["boil_temperature"] == 100.0


def test_repository_control_validation_rejects_missing_fields_without_write(
    isolated_sqlite, tmp_path, monkeypatch
):
    candidate = _candidate(isolated_sqlite, tmp_path)
    monkeypatch.setenv("TESSERACT_BRIDGE_STORAGE_MODE", "orm")
    monkeypatch.setenv("TESSERACT_BRIDGE_SIMULATION_ONLY", "1")
    monkeypatch.setenv("TESSERACT_BRIDGE_DB", str(isolated_sqlite))
    repo = NormalizedRepository(candidate)
    old_revision = repo.control_revision()
    data = repo.control_profile()
    del data["mash_curve"]
    with pytest.raises(ValueError, match="exatamente os campos"):
        repo.save_control_profile(data, expected_revision=old_revision)
    assert repo.control_revision() == old_revision
