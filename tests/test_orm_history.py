"""Alembic 0003: lossless administrative history, even after recipe deletion."""
import copy
import json

import pytest
from sqlalchemy import select

from storage import sqlite_store as store
from storage.history_mapper import decode_document
from storage.models import AuditEvent, ConfigurationDraft, RecipeRevision, session_scope
from storage.orm_audit import audit_copy
from storage.orm_normalize import NormalizationError, normalize_copy
from storage.repositories.orm import NormalizedRepository


def populated_history(isolated_sqlite, tmp_path):
    from tests.test_data_store import config, recipe

    config()
    rid = "private:historico"
    store.create_recipe(rid, "private", recipe("Primeira versão"))
    updated = recipe("Segunda versão")
    store.update_recipe(rid, updated)
    active = store.load_config()
    draft = copy.deepcopy(active)
    draft["devices"][0]["name"] = "Sensor renomeado"
    draft_id = store.save_draft(draft)
    store.activate_draft(draft_id)
    # Deleting the current recipe must never delete immutable revisions.
    store.delete_recipe(rid)
    detail = {
        "tag": "histórico",
        "nested": [{"enabled": True, "count": 3, "ratio": 0.25},
                   {"empty": [], "none": None, "object": {}}],
        "unicode": "çãé",
    }
    with store.connection(writable=True) as conn:
        conn.execute(
            "INSERT INTO audit_events(event_type,details_json) VALUES(?,?)",
            ("typed_history_test", store.dumps(detail))
        )
        conn.execute(
            "INSERT INTO legacy_imports(source_sha256,manifest_json) VALUES(?,?)",
            ("b" * 64, store.dumps({"files": ["a.yml", "b.json"],
                                  "repairs": [{"device_id": "pump", "before": True,
                                               "after": False}]}))
        )
    candidate = tmp_path / "normalized-v3.sqlite3"
    normalize_copy(source=isolated_sqlite, destination=candidate)
    return candidate, detail, draft_id


def test_history_roundtrip_including_deleted_recipe_and_nested_values(
    isolated_sqlite, tmp_path
):
    candidate, detail, draft_id = populated_history(isolated_sqlite, tmp_path)
    result = audit_copy(source=isolated_sqlite, candidate=candidate)
    assert result["result"] == "OK"
    assert result["alembic"] == "bridge_orm_0003"
    assert result["history_configuration_drafts"] == 1
    assert result["history_legacy_imports"] == 1
    assert result["history_recipe_revisions"] == 2
    assert result["history_schema_migrations"] >= 2
    repo = NormalizedRepository(candidate)
    assert repo.recipe("private:historico") is None
    assert repo.history_counts()["recipe_revisions"] == 2
    with session_scope(candidate, readonly=True) as session:
        old = session.get(RecipeRevision, ("private:historico", 1))
        new = session.get(RecipeRevision, ("private:historico", 2))
        assert decode_document(old.document)["name"] == "Primeira versão"
        assert decode_document(new.document)["name"] == "Segunda versão"
        assert session.get(ConfigurationDraft, draft_id).status == "applied"
        record = session.scalars(
            select(AuditEvent).where(AuditEvent.event_type == "typed_history_test")
        ).one()
        assert decode_document(record.document) == detail


def test_history_audit_detects_modified_typed_node(isolated_sqlite, tmp_path):
    candidate, _, _ = populated_history(isolated_sqlite, tmp_path)
    with session_scope(candidate) as session:
        record = session.scalars(
            select(AuditEvent).where(AuditEvent.event_type == "typed_history_test")
        ).one()
        node = next(node for node in record.document.nodes
                    if node.key == "tag" and node.value_kind == "str")
        node.text_value = "adulterado"
    with pytest.raises(NormalizationError, match="Hash|histórico"):
        audit_copy(source=isolated_sqlite, candidate=candidate)


def test_history_audit_detects_deleted_draft(isolated_sqlite, tmp_path):
    candidate, _, draft_id = populated_history(isolated_sqlite, tmp_path)
    with session_scope(candidate) as session:
        session.delete(session.get(ConfigurationDraft, draft_id))
    with pytest.raises(NormalizationError, match="Histórico"):
        audit_copy(source=isolated_sqlite, candidate=candidate)


def test_history_source_not_modified_during_normalization(isolated_sqlite, tmp_path):
    from tests.test_data_store import config
    config()
    original = isolated_sqlite.read_bytes()
    candidate = tmp_path / "no-side-effects.sqlite3"
    normalize_copy(source=isolated_sqlite, destination=candidate)
    assert isolated_sqlite.read_bytes() == original
    with session_scope(candidate, readonly=True) as session:
        assert session.get(RecipeRevision, ("missing", 1)) is None


def test_empty_and_scalar_historical_documents(isolated_sqlite, tmp_path):
    with store.connection(writable=True) as conn:
        for value in ([], {}, False, 0, "", None, [None, False, [], {}]):
            conn.execute(
                "INSERT INTO audit_events(event_type,details_json) VALUES(?,?)",
                ("variety", store.dumps(value))
            )
    candidate = tmp_path / "variety.sqlite3"
    normalize_copy(source=isolated_sqlite, destination=candidate)
    assert audit_copy(source=isolated_sqlite, candidate=candidate)["result"] == "OK"


def test_history_audit_detects_changed_document_kind(isolated_sqlite, tmp_path):
    candidate, _, _ = populated_history(isolated_sqlite, tmp_path)
    with session_scope(candidate) as session:
        event = session.scalars(
            select(AuditEvent).where(AuditEvent.event_type == "typed_history_test")
        ).one()
        event.document.kind = "configuration_revision"
    with pytest.raises(NormalizationError, match="Tipo de documento"):
        audit_copy(source=isolated_sqlite, candidate=candidate)
