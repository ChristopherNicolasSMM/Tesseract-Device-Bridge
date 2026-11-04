"""Isolated SQLite per pytest test. Never touches a real Pi database."""
import pytest
from storage import sqlite_store as store


@pytest.fixture(autouse=True)
def isolated_sqlite(tmp_path, monkeypatch):
    db = tmp_path / "isolated-bridge.sqlite3"
    # Running pytest in an interactive ORM shell must not select that backend
    # for a legacy-only fixture. ORM tests explicitly opt in per test.
    monkeypatch.setenv("TESSERACT_BRIDGE_STORAGE_MODE", "legacy")
    monkeypatch.setenv("TESSERACT_BRIDGE_DB", str(db))
    store.initialize(path=db)
    yield db
