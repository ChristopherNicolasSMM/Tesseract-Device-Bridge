"""Read-only integrity audit between a JSON-backed SQLite and its ORM copy.

Checks historical tables byte-for-byte as database rows, in addition to
model/domain equivalence. No SQLite writes, GPIO calls, or credentials printed.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from storage.orm_normalize import _legacy_snapshot, _verify, NormalizationError
from storage.repositories.orm import NormalizedRepository
from storage.session_mapper import read_operational_snapshot
from config import BridgeConfig


# These remain in the original schema until normalized models are implemented.
# The ORM copy must still preserve their historical data without modification.
LEGACY_PRESERVED_TABLES = (
    "active_recipe",
    "audit_events",
    "configuration_drafts",
    "configuration_revisions",
    "legacy_imports",
    "recipe_revisions",
    "schema_migrations",
    "sensor_calibrations",
    "session_state",
)


def _read_only_connection(path):
    # mode=ro refuses missing files; avoids creating a new database by mistake.
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def _table_digest(connection, table):
    # Hard-coded allowlist above. No user-supplied identifiers reach SQL.
    cursor = connection.execute("SELECT * FROM " + table)
    columns = [description[0] for description in cursor.description]
    rows = sorted(
        json.dumps(dict(zip(columns, row)), ensure_ascii=False,
                   sort_keys=True, separators=(",", ":"))
        for row in cursor
    )
    digest = hashlib.sha256()
    for value in rows:
        digest.update(value.encode("utf-8"))
        digest.update(b"\n")
    return len(rows), digest.hexdigest()


def audit_copy(*, source, candidate):
    """Verify pre-existing and normalized data, without modifying either DB."""
    original = Path(source).expanduser().resolve()
    normalized = Path(candidate).expanduser().resolve()
    if original == normalized:
        raise NormalizationError("A origem e a cópia devem ser arquivos diferentes.")
    if not original.is_file() or not normalized.is_file():
        raise NormalizationError("Origem ou cópia ORM inexistente.")

    for path in (original, normalized):
        with _read_only_connection(path) as connection:
            if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise NormalizationError("Falha de integridade SQLite: " + str(path))

    snapshot = _legacy_snapshot(original)
    with _read_only_connection(normalized) as target:
        alembic = target.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        if not alembic or alembic[0] != "bridge_orm_0002":
            raise NormalizationError(
                "Cópia normalizada com revisão antiga. Gere uma NOVA cópia "
                "com 'normalize --output ...normalized-v2.sqlite3'; "
                "não sobrescreva o arquivo anterior."
            )
    operational = read_operational_snapshot(
        original, devices=BridgeConfig.from_dict(snapshot[0]).devices
    )
    counts = _verify(normalized, snapshot, operational)
    repo = NormalizedRepository(normalized)
    # Strong guard against missing core model records.
    if len(repo.configuration()["devices"]) != counts["devices"]:
        raise NormalizationError("Número de dispositivos ORM divergente.")
    if len(repo.list_recipes()) != counts["recipes"]:
        raise NormalizationError("Número de receitas ORM divergente.")
    if repo.configuration_revision() != counts["revision"]:
        raise NormalizationError("Revisão de configuração ORM divergente.")

    preserved = {}
    with _read_only_connection(original) as legacy, _read_only_connection(normalized) as target:
        for table in LEGACY_PRESERVED_TABLES:
            src = _table_digest(legacy, table)
            dst = _table_digest(target, table)
            if src != dst:
                raise NormalizationError(
                    "Cópia ORM diverge dos dados históricos da tabela " + table
                )
            preserved[table] = src[0]
        alembic = target.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        if not alembic or alembic[0] != "bridge_orm_0002":
            raise NormalizationError("Versão Alembic inesperada na cópia.")

    return {
        "result": "OK",
        "source": str(original),
        "candidate": str(normalized),
        "alembic": "bridge_orm_0002",
        **counts,
        "legacy_preserved_rows": preserved,
        "runtime_cutover_enabled": False,
    }
