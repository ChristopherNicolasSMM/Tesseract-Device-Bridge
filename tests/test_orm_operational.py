"""Operational ORM normalization regressions. No physical runtime and no dual writes."""
from dataclasses import asdict

import pytest

from recipe_engine.state import RecipeState
from storage import sqlite_store as store
from storage.orm_audit import audit_copy
from storage.orm_normalize import normalize_copy, NormalizationError
from storage.repositories.orm import NormalizedRepository
from storage.models import session_scope, SensorCalibration, SessionAlarm


def populated_candidate(isolated_sqlite, tmp_path):
    from tests.test_data_store import config, recipe
    cfg = config()
    rid = "private:hot-trial"
    store.create_recipe(rid, "private", recipe("Hot Trial"))
    store.set_active_recipe(rid)
    store.save_calibrations({"schema": 1, "sensors": {
        "demo_temperature": {"address": None, "offset_c": 2.1}
    }})
    state = asdict(RecipeState.fresh("Hot Trial"))
    state.update({
        "status": "paused_after_crash",
        "paused_from_status": "holding",
        "next_alarm_id": 9,
        "control_settings": store.load_control(),
        "pending_alarms": [
            {"id": 7, "type": "hop_addition", "label": "Lúpulo",
             "fired_at": 173.5},
            {"id": 8, "type": "vessel_end", "label": "Mostura encerrada",
             "fired_at": 194.0},
        ],
        "fired_hop_alarm_keys": ["1:0", "1:1"],
    })
    store.save_session_state(state)
    path = tmp_path / "candidate-orm-v2.sqlite3"
    normalize_copy(source=isolated_sqlite, destination=path)
    return path, rid, state


def test_operational_data_round_trips_via_models(isolated_sqlite, tmp_path):
    candidate, rid, snapshot = populated_candidate(isolated_sqlite, tmp_path)
    repo = NormalizedRepository(candidate)
    assert repo.active_recipe() == rid
    assert repo.calibrations() == {"schema": 1, "sensors": {
        "demo_temperature": {"address": None, "offset_c": 2.1}
    }}
    assert repo.session_state() == snapshot
    result = audit_copy(source=isolated_sqlite, candidate=candidate)
    assert result["result"] == "OK"
    assert result["alembic"] == "bridge_orm_0003"
    assert result["calibrations"] == 1
    assert result["active_recipe"] == 1
    assert result["session_state"] == 1
    assert result["pending_alarms"] == 2


def test_calibration_tampering_is_detected(isolated_sqlite, tmp_path):
    candidate, _, _ = populated_candidate(isolated_sqlite, tmp_path)
    with session_scope(candidate) as session:
        session.get(SensorCalibration, "demo_temperature").offset_c = -2.1
    with pytest.raises(NormalizationError, match="Calibrações"):
        audit_copy(source=isolated_sqlite, candidate=candidate)


def test_pending_alarm_tampering_is_detected(isolated_sqlite, tmp_path):
    candidate, _, _ = populated_candidate(isolated_sqlite, tmp_path)
    with session_scope(candidate) as session:
        first = session.get(SessionAlarm, (1, 7))
        first.label = "alterado"
    with pytest.raises(NormalizationError, match="alarmes"):
        audit_copy(source=isolated_sqlite, candidate=candidate)


def test_old_candidate_revision_gets_safe_instruction(isolated_sqlite, tmp_path):
    candidate, _, _ = populated_candidate(isolated_sqlite, tmp_path)
    import sqlite3
    with sqlite3.connect(str(candidate)) as conn:
        conn.execute("UPDATE alembic_version SET version_num='bridge_orm_0001'")
    with pytest.raises(NormalizationError, match="NOVA cópia"):
        audit_copy(source=isolated_sqlite, candidate=candidate)


def test_missing_session_and_calibration_do_not_seed_unwanted_rows(isolated_sqlite, tmp_path):
    candidate = tmp_path / "empty-operational.sqlite3"
    normalize_copy(source=isolated_sqlite, destination=candidate)
    repo = NormalizedRepository(candidate)
    assert repo.active_recipe() is None
    assert repo.calibrations() == {"schema": 1, "sensors": {}}
    assert repo.session_state() is None
    result = audit_copy(source=isolated_sqlite, candidate=candidate)
    assert result["session_state"] == 0
    assert result["calibrations"] == 0



def test_repository_refuses_stale_orm_revision(isolated_sqlite, tmp_path):
    candidate, _, _ = populated_candidate(isolated_sqlite, tmp_path)
    import sqlite3
    from storage.repositories.orm import RepositoryError
    with sqlite3.connect(str(candidate)) as conn:
        conn.execute("UPDATE alembic_version SET version_num='bridge_orm_0001'")
    with pytest.raises(RepositoryError, match="revisão antiga"):
        NormalizedRepository(candidate)


def test_audit_explains_when_legacy_source_session_changes_after_copy(
    isolated_sqlite, tmp_path
):
    candidate, _, _ = populated_candidate(isolated_sqlite, tmp_path)
    import sqlite3
    with sqlite3.connect(str(isolated_sqlite)) as conn:
        conn.execute(
            "UPDATE session_state SET updated_at=? WHERE id=1",
            ("2099-01-01 12:00:00",),
        )
    with pytest.raises(NormalizationError, match="Origem alterada após a cópia ORM"):
        audit_copy(source=isolated_sqlite, candidate=candidate)
    with sqlite3.connect(str(candidate)) as conn:
        expected = conn.execute(
            "SELECT updated_at FROM bridge_session_state_v2 WHERE id=1"
        ).fetchone()[0]
        assert expected != "2099-01-01 12:00:00"


def test_audit_explains_when_orm_runtime_changes_session_after_copy(
    isolated_sqlite, tmp_path
):
    candidate, _, _ = populated_candidate(isolated_sqlite, tmp_path)
    import sqlite3
    with sqlite3.connect(str(candidate)) as conn:
        conn.execute(
            "UPDATE bridge_session_state_v2 SET updated_at=? WHERE id=1",
            ("2099-02-02 12:00:00",),
        )
    with pytest.raises(NormalizationError, match="Estado relacional da cópia ORM diferente"):
        audit_copy(source=isolated_sqlite, candidate=candidate)


def test_audit_explains_when_candidate_legacy_snapshot_is_edited(
    isolated_sqlite, tmp_path
):
    candidate, _, _ = populated_candidate(isolated_sqlite, tmp_path)
    import sqlite3
    with sqlite3.connect(str(candidate)) as conn:
        conn.execute(
            "UPDATE session_state SET updated_at=? WHERE id=1",
            ("2099-03-03 12:00:00",),
        )
    with pytest.raises(NormalizationError, match="Snapshot legado da cópia ORM alterado"):
        audit_copy(source=isolated_sqlite, candidate=candidate)



def test_cli_orm_audit_prints_readable_error_without_traceback(
    isolated_sqlite, tmp_path, monkeypatch
):
    import os
    import sqlite3
    import subprocess
    import sys
    from tesseract_bridge.infrastructure.paths import PROJECT_ROOT

    candidate, _, _ = populated_candidate(isolated_sqlite, tmp_path)
    with sqlite3.connect(str(isolated_sqlite)) as conn:
        conn.execute(
            "UPDATE session_state SET updated_at=? WHERE id=1",
            ("2099-04-04 12:00:00",),
        )

    env = {**os.environ,
           "TESSERACT_BRIDGE_DB": str(isolated_sqlite),
           "TESSERACT_BRIDGE_STORAGE_MODE": "legacy"}
    run = subprocess.run(
        [sys.executable, "-m", "storage.cli", "orm-audit",
         "--candidate", str(candidate)],
        cwd=str(PROJECT_ROOT), env=env, capture_output=True,
        text=True, timeout=30,
    )
    assert run.returncode == 2
    assert "Auditoria ORM reprovada" in run.stderr
    assert "Origem alterada após a cópia ORM" in run.stderr
    assert "Traceback" not in run.stderr
