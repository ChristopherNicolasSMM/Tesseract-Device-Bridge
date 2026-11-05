"""Isolated SQLite per pytest test. Never touches a real Pi database."""
import pytest
from storage import sqlite_store as store


@pytest.fixture(autouse=True)
def isolated_sqlite(tmp_path, monkeypatch):
    db = tmp_path / "isolated-bridge.sqlite3"
    # New credential policy is opt-in per test, independent of the developer shell.
    monkeypatch.setenv("TESSERACT_BRIDGE_ADMIN_TOKEN_B64", "")
    monkeypatch.setenv("TESSERACT_BRIDGE_LOCAL_ADMIN", "")
    monkeypatch.setenv("TESSERACT_BRIDGE_INSTALL_ID", "")
    monkeypatch.setattr("tesseract_bridge.infrastructure.installation.PROJECT_ROOT", tmp_path / "receipt-sandbox")
    # Running pytest in an interactive ORM shell must not select that backend
    # for a legacy-only fixture. ORM tests explicitly opt in per test.
    monkeypatch.setenv("TESSERACT_BRIDGE_STORAGE_MODE", "legacy")
    monkeypatch.setenv("TESSERACT_BRIDGE_DB", str(db))
    store.initialize(path=db)
    yield db
