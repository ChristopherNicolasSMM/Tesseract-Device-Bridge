"""Read-only integrity audit between a JSON-backed SQLite and its ORM copy.

Checks historical tables byte-for-byte as database rows, in addition to
model/domain equivalence. No SQLite writes, GPIO calls, or credentials printed.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from storage.orm_normalize import _legacy_snapshot, _verify, NormalizationError
from storage.repositories.orm import NormalizedRepository
from storage.session_mapper import read_operational_snapshot
from storage.history_mapper import read_history_snapshot
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



def _session_timestamp(connection, table):
    """Use fixed table identifiers only; never inspect or display session JSON."""
    row = connection.execute(
        "SELECT updated_at FROM " + table + " WHERE id=1"
    ).fetchone()
    return row[0] if row else None


def _check_session_snapshot_age(source, candidate):
    """Classify session divergence before comparing immutable ORM snapshots.

    The audit is a strict migration equivalence check, NOT a consistency
    comparison between a running source and its later-edited ORM clone.
    Both files are opened read-only. No state contents are printed.
    """
    with closing(_read_only_connection(source)) as original:
        original_time = _session_timestamp(original, "session_state")
    with closing(_read_only_connection(candidate)) as normalized:
        copied_time = _session_timestamp(normalized, "session_state")
        orm_time = _session_timestamp(normalized, "bridge_session_state_v2")

    if original_time != copied_time:
        if copied_time == orm_time:
            cause = (
                "Origem alterada após a cópia ORM: a tabela legada preservada "
                "e o modelo ORM concordam entre si, mas não com a origem."
            )
        elif original_time == orm_time:
            cause = (
                "Snapshot legado da cópia ORM alterado após a migração: "
                "a origem concorda com o modelo ORM, mas não com a tabela legada."
            )
        else:
            cause = (
                "Origem e snapshot legado da cópia divergem; o modelo ORM "
                "também tem outro timestamp. Ambos os bancos precisam ser "
                "verificados antes de uma nova normalização."
            )
        raise NormalizationError(
            f"{cause} Timestamps: origem={original_time!r}, "
            f"cópia_legada={copied_time!r}, cópia_orm={orm_time!r}. "
            "Pare o Bridge, confira o banco apontado pelo .env e gere uma "
            "NOVA cópia com 'normalize --output ...' (outro nome); "
            "não apague nem sobrescreva os bancos existentes."
        )
    if copied_time != orm_time:
        raise NormalizationError(
            "Estado relacional da cópia ORM diferente do snapshot feito "
            f"na migração: timestamp legado={copied_time!r}, "
            f"ORM={orm_time!r}. "
            "A cópia candidata pode ter sido usada pelo runtime ORM ou "
            "modificada após a migração. Preserve-a e gere uma NOVA "
            "cópia para repetir a auditoria; não desative a comparação."
        )


def audit_copy(*, source, candidate):
    """Verify pre-existing and normalized data, without modifying either DB."""
    original = Path(source).expanduser().resolve()
    normalized = Path(candidate).expanduser().resolve()
    if original == normalized:
        raise NormalizationError("A origem e a cópia devem ser arquivos diferentes.")
    if not original.is_file() or not normalized.is_file():
        raise NormalizationError("Origem ou cópia ORM inexistente.")

    for path in (original, normalized):
        with closing(_read_only_connection(path)) as connection:
            if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise NormalizationError("Falha de integridade SQLite: " + str(path))

    snapshot = _legacy_snapshot(original)
    with closing(_read_only_connection(normalized)) as target:
        alembic = target.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        if not alembic or alembic[0] != "bridge_orm_0003":
            raise NormalizationError(
                "Cópia normalizada com revisão antiga. Gere uma NOVA cópia "
                "com 'normalize --output ...normalized-v3.sqlite3'; "
                "não sobrescreva o arquivo anterior."
            )
    # Check version before accessing _v2 tables: a real 0001 candidate
    # may not contain the operational ORM model at all.
    _check_session_snapshot_age(original, normalized)
    operational = read_operational_snapshot(
        original, devices=BridgeConfig.from_dict(snapshot[0]).devices
    )
    history = read_history_snapshot(original)
    counts = _verify(normalized, snapshot, operational, history)
    repo = NormalizedRepository(normalized)
    # Strong guard against missing core model records.
    if len(repo.configuration()["devices"]) != counts["devices"]:
        raise NormalizationError("Número de dispositivos ORM divergente.")
    if len(repo.list_recipes()) != counts["recipes"]:
        raise NormalizationError("Número de receitas ORM divergente.")
    if repo.configuration_revision() != counts["revision"]:
        raise NormalizationError("Revisão de configuração ORM divergente.")

    preserved = {}
    with closing(_read_only_connection(original)) as legacy, closing(_read_only_connection(normalized)) as target:
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
        if not alembic or alembic[0] != "bridge_orm_0003":
            raise NormalizationError("Versão Alembic inesperada na cópia.")

    return {
        "result": "OK",
        "source": str(original),
        "candidate": str(normalized),
        "alembic": "bridge_orm_0003",
        **counts,
        "legacy_preserved_rows": preserved,
        "runtime_cutover_enabled": False,
    }
