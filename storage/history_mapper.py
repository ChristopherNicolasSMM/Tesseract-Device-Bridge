"""Lossless normalized history: typed tree rows, no JSON columns.

Operational models stay domain-specific; historical documents can contain
old schemas and arbitrary metadata, so are represented by typed nodes.
"""
from __future__ import annotations

import hashlib
import json
import math

from sqlalchemy import select
from storage import sqlite_store as store
from storage.mappers import NormalizationError
from storage.models import (
    AuditEvent, ConfigurationDraft, ConfigurationRevision, HistoryDocument,
    HistoryNode, LegacyImport, LegacySchemaMigration, RecipeRevision,
)

_QUERIES = {
    "configuration_revisions": "SELECT revision,snapshot_json,action,created_at FROM configuration_revisions ORDER BY revision",
    "configuration_drafts": "SELECT id,payload_json,base_revision,status,created_at FROM configuration_drafts ORDER BY id",
    "recipe_revisions": "SELECT recipe_id,revision,recipe_json,created_at FROM recipe_revisions ORDER BY recipe_id,revision",
    "audit_events": "SELECT id,event_type,entity_id,details_json,created_at FROM audit_events ORDER BY id",
    "legacy_imports": "SELECT source_sha256,manifest_json,created_at FROM legacy_imports ORDER BY source_sha256",
    "schema_migrations": "SELECT version,filename,sha256,applied_at FROM schema_migrations ORDER BY version",
}
_PAYLOAD = {
    "configuration_revisions": "snapshot_json",
    "configuration_drafts": "payload_json",
    "recipe_revisions": "recipe_json",
    "audit_events": "details_json",
    "legacy_imports": "manifest_json",
}
_MAX_DEPTH = 64
_MAX_NODES = 100000


def _validate_value(value, depth=0, count=None):
    if count is None:
        count = [0]
    count[0] += 1
    if depth > _MAX_DEPTH or count[0] > _MAX_NODES:
        raise NormalizationError("Documento histórico excede limites de profundidade/tamanho.")
    if value is None or type(value) in (bool, str):
        return
    if type(value) is int:
        if not -(2 ** 63) <= value < 2 ** 63:
            raise NormalizationError("Inteiro histórico fora dos limites do SQLite.")
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise NormalizationError("Float histórico NaN/Infinito não permitido.")
        return
    if isinstance(value, list):
        for child in value:
            _validate_value(child, depth + 1, count)
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise NormalizationError("Chave histórica não é string.")
            _validate_value(child, depth + 1, count)
        return
    raise NormalizationError("Tipo histórico não suportado: " + type(value).__name__)


def read_history_snapshot(path):
    """Read historic rows without modifying the database."""
    result = {}
    with store.connection(path=path) as conn:
        for table, sql in _QUERIES.items():
            records = [dict(row) for row in conn.execute(sql)]
            field = _PAYLOAD.get(table)
            if field:
                for record in records:
                    try:
                        record[field] = json.loads(record[field])
                    except (TypeError, ValueError) as exc:
                        raise NormalizationError("Payload histórico inválido: " + table) from exc
                    _validate_value(record[field])
            result[table] = records
    return result


def _document(kind, value):
    _validate_value(value)
    doc = HistoryDocument(
        kind=kind, sha256=hashlib.sha256(store.dumps(value).encode("utf-8")).hexdigest()
    )

    def append(payload, parent, key, ordinal):
        args = {"document": doc, "parent": parent, "key": key, "ordinal": ordinal}
        if isinstance(payload, dict):
            args["value_kind"] = "object"
        elif isinstance(payload, list):
            args["value_kind"] = "array"
        elif payload is None:
            args["value_kind"] = "null"
        elif type(payload) is bool:
            args.update(value_kind="bool", bool_value=payload)
        elif type(payload) is int:
            args.update(value_kind="int", int_value=payload)
        elif type(payload) is float:
            args.update(value_kind="float", float_value=payload)
        else:
            args.update(value_kind="str", text_value=payload)
        node = HistoryNode(**args)
        if isinstance(payload, dict):
            for index, (k, child) in enumerate(payload.items()):
                append(child, node, k, index)
        elif isinstance(payload, list):
            for index, child in enumerate(payload):
                append(child, node, None, index)

    append(value, None, None, 0)
    return doc


def decode_document(doc):
    if doc is None:
        raise NormalizationError("Documento histórico ausente.")
    nodes = list(doc.nodes)
    roots = [node for node in nodes if node.parent_id is None]
    if len(roots) != 1 or roots[0].ordinal != 0 or roots[0].key is not None:
        raise NormalizationError("Documento histórico sem raiz única.")
    children = {}
    for node in nodes:
        children.setdefault(node.parent_id, []).append(node)
    visited = set()

    def walk(node, depth):
        if node.id in visited or depth > _MAX_DEPTH:
            raise NormalizationError("Árvore histórica inválida/cíclica.")
        visited.add(node.id)
        descendants = sorted(children.get(node.id, []), key=lambda item: item.ordinal)
        if [child.ordinal for child in descendants] != list(range(len(descendants))):
            raise NormalizationError("Ordem histórica divergente.")
        if node.value_kind == "object":
            if any(child.key is None for child in descendants):
                raise NormalizationError("Objeto histórico sem chave.")
            result = {child.key: walk(child, depth + 1) for child in descendants}
            if len(result) != len(descendants):
                raise NormalizationError("Chaves históricas duplicadas.")
            return result
        if node.value_kind == "array":
            if any(child.key is not None for child in descendants):
                raise NormalizationError("Array histórico com chave.")
            return [walk(child, depth + 1) for child in descendants]
        if descendants:
            raise NormalizationError("Escalar histórico contém filhos.")
        if node.value_kind == "null":
            return None
        if node.value_kind == "bool":
            return bool(node.bool_value)
        if node.value_kind == "int":
            return node.int_value
        if node.value_kind == "float":
            return node.float_value
        if node.value_kind == "str":
            return node.text_value
        raise NormalizationError("Tipo histórico não reconhecido.")

    result = walk(roots[0], 0)
    if len(visited) != len(nodes):
        raise NormalizationError("Nós históricos desconectados.")
    _validate_value(result)
    digest = hashlib.sha256(store.dumps(result).encode("utf-8")).hexdigest()
    if digest != doc.sha256:
        raise NormalizationError("Hash do documento histórico divergente.")
    return result


def persist_history(session, history):
    for r in history["configuration_revisions"]:
        session.add(ConfigurationRevision(
            revision=r["revision"], action=r["action"], created_at=r["created_at"],
            document=_document("configuration_revision", r["snapshot_json"]),
        ))
    for r in history["configuration_drafts"]:
        session.add(ConfigurationDraft(
            id=r["id"], base_revision=r["base_revision"],
            status=r["status"], created_at=r["created_at"],
            document=_document("configuration_draft", r["payload_json"]),
        ))
    for r in history["recipe_revisions"]:
        session.add(RecipeRevision(
            recipe_id=r["recipe_id"], revision=r["revision"],
            created_at=r["created_at"],
            document=_document("recipe_revision", r["recipe_json"]),
        ))
    for r in history["audit_events"]:
        session.add(AuditEvent(
            id=r["id"], event_type=r["event_type"], entity_id=r["entity_id"],
            created_at=r["created_at"],
            document=_document("audit_event", r["details_json"]),
        ))
    for r in history["legacy_imports"]:
        session.add(LegacyImport(
            source_sha256=r["source_sha256"], created_at=r["created_at"],
            document=_document("legacy_import", r["manifest_json"]),
        ))
    for r in history["schema_migrations"]:
        session.add(LegacySchemaMigration(**r))


def _owned_document(doc, expected_kind):
    if doc is None or doc.kind != expected_kind:
        raise NormalizationError("Tipo de documento histórico incompatível.")
    return decode_document(doc)


def history_rows(session):
    return {
        "configuration_revisions": [
            dict(revision=r.revision, snapshot_json=_owned_document(r.document, "configuration_revision"),
                 action=r.action, created_at=r.created_at)
            for r in session.scalars(select(ConfigurationRevision).order_by(ConfigurationRevision.revision))
        ],
        "configuration_drafts": [
            dict(id=r.id, payload_json=_owned_document(r.document, "configuration_draft"),
                 base_revision=r.base_revision, status=r.status, created_at=r.created_at)
            for r in session.scalars(select(ConfigurationDraft).order_by(ConfigurationDraft.id))
        ],
        "recipe_revisions": [
            dict(recipe_id=r.recipe_id, revision=r.revision,
                 recipe_json=_owned_document(r.document, "recipe_revision"), created_at=r.created_at)
            for r in session.scalars(select(RecipeRevision).order_by(
                RecipeRevision.recipe_id, RecipeRevision.revision))
        ],
        "audit_events": [
            dict(id=r.id, event_type=r.event_type, entity_id=r.entity_id,
                 details_json=_owned_document(r.document, "audit_event"), created_at=r.created_at)
            for r in session.scalars(select(AuditEvent).order_by(AuditEvent.id))
        ],
        "legacy_imports": [
            dict(source_sha256=r.source_sha256, manifest_json=_owned_document(r.document, "legacy_import"),
                 created_at=r.created_at)
            for r in session.scalars(select(LegacyImport).order_by(LegacyImport.source_sha256))
        ],
        "schema_migrations": [
            dict(version=r.version, filename=r.filename, sha256=r.sha256,
                 applied_at=r.applied_at)
            for r in session.scalars(select(LegacySchemaMigration).order_by(LegacySchemaMigration.version))
        ],
    }


def verify_history(session, history):
    actual = history_rows(session)
    for table, records in history.items():
        if actual[table] != records:
            raise NormalizationError("Histórico relacional divergente: " + table)
    return {"history_" + table: len(records) for table, records in history.items()}
