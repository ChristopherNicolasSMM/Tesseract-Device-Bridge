"""SQLite migrations, intentionally compatible with Python 3.9 and bundled SQLite.

No implicit YAML fallback. Schema migrations are versioned SQL files.
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


class StorageError(RuntimeError):
    pass


def apply_migrations(db_path):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=15)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA synchronous=FULL")
        check = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        applied = {}
        if check:
            applied = dict(conn.execute("SELECT version, sha256 FROM schema_migrations").fetchall())
        for filename in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if not filename.name[:4].isdigit():
                raise StorageError("Migração sem número: " + filename.name)
            version = int(filename.name[:4])
            source = filename.read_text(encoding="utf-8")
            checksum = hashlib.sha256(source.encode("utf-8")).hexdigest()
            if version in applied:
                if applied[version] != checksum:
                    raise StorageError("Migração SQL já aplicada foi modificada: " + filename.name)
                continue
            # A SQL file is part of our packaged code, not supplied by the operator.
            # executescript requires explicit BEGIN/COMMIT to guarantee atomic migrations.
            escaped = filename.name.replace("'", "''")
            script = ("BEGIN IMMEDIATE;\n" + source + "\n"
                      "INSERT INTO schema_migrations(version,filename,sha256) VALUES"
                      f"({version},'{escaped}','{checksum}');\nCOMMIT;")
            try:
                conn.executescript(script)
            except Exception:
                if conn.in_transaction:
                    conn.rollback()
                raise
        versions = [int(f.name[:4]) for f in MIGRATIONS_DIR.glob("*.sql")]
        if not versions or len(set(versions)) != len(versions):
            raise StorageError("Migrações ausentes ou com número duplicado.")
    finally:
        conn.close()
    try:
        db_path.chmod(0o600)
    except OSError:
        pass


def check_schema(conn):
    if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise StorageError("Banco SQLite não passou na verificação de integridade.")
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {"schema_migrations", "system_config", "devices", "recipes", "settings", "session_state"} <= names:
        raise StorageError("Banco sem migrações obrigatórias; execute a inicialização SQLite.")
