"""New boot setup uses SQLite only, without recreating YAML files."""
import pytest
from storage import sqlite_store as store


def test_clean_database_bootstrap(isolated_sqlite):
    assert isolated_sqlite.exists()
    assert store.load_config()["backend"] == "simulated"


def test_bootstrap_does_not_overwrite_config(isolated_sqlite):
    config=store.load_config()
    config["devices"][0]["name"]="Alterado"
    store.apply_config(config)
    store.initialize()
    assert store.load_config()["devices"][0]["name"]=="Alterado"


def test_missing_db_requires_explicit_initialize(tmp_path, monkeypatch):
    target=tmp_path/"never-created.sqlite3"
    monkeypatch.setenv("TESSERACT_BRIDGE_DB",str(target))
    with pytest.raises(Exception,match="não encontrado"):
        store.load_config()
    assert not target.exists()
