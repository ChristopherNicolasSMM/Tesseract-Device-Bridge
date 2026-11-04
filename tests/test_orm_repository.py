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
