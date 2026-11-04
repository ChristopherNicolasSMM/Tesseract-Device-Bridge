"""Cross-platform .env infrastructure, without modifying production SQLite."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from infra_env import flag, load_infra_env, port
from project_paths import PROJECT_ROOT
from storage import sqlite_store as store
from storage.launch_config import load_runtime_config
from storage.migrate import StorageError


def test_dotenv_loads_settings_without_shell_export(tmp_path, monkeypatch):
    config = tmp_path / ".env"
    config.write_text(
        "TESSERACT_BRIDGE_SIMULATION_ONLY=1\n"
        "TESSERACT_BRIDGE_TEST_PANEL_PORT=8098\n"
        "TESSERACT_BRIDGE_ADMIN_TOKEN=an-isolated-test-token-abc\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("TESSERACT_BRIDGE_SIMULATION_ONLY", raising=False)
    monkeypatch.delenv("TESSERACT_BRIDGE_TEST_PANEL_PORT", raising=False)
    monkeypatch.delenv("TESSERACT_BRIDGE_ADMIN_TOKEN", raising=False)
    assert load_infra_env(config)
    assert flag("TESSERACT_BRIDGE_SIMULATION_ONLY")
    assert port("TESSERACT_BRIDGE_TEST_PANEL_PORT") == 8098
    assert os.environ["TESSERACT_BRIDGE_ADMIN_TOKEN"] == "an-isolated-test-token-abc"


def test_existing_shell_values_win_over_dotenv(tmp_path, monkeypatch):
    config = tmp_path / ".env"
    config.write_text("TESSERACT_BRIDGE_TEST_PANEL_PORT=9999\n", encoding="utf-8")
    monkeypatch.setenv("TESSERACT_BRIDGE_TEST_PANEL_PORT", "8181")
    load_infra_env(config)
    assert os.environ["TESSERACT_BRIDGE_TEST_PANEL_PORT"] == "8181"


def test_missing_dotenv_does_not_break_startup(tmp_path):
    assert load_infra_env(tmp_path / ".env") is False


def test_relative_sqlite_path_anchored_to_repository(tmp_path, monkeypatch):
    monkeypatch.setenv("TESSERACT_BRIDGE_DB", "./data/private/from-dotenv.sqlite3")
    monkeypatch.chdir(tmp_path)
    assert store.db_path() == (PROJECT_ROOT / "data/private/from-dotenv.sqlite3").resolve()


def test_simulation_guards_gpio_mqtt_and_uses_test_port(monkeypatch):
    initial = store.load_config()
    initial["backend"] = "real"
    initial["mqtt"]["enabled"] = True
    store.apply_config(initial)
    monkeypatch.setenv("TESSERACT_BRIDGE_SIMULATION_ONLY", "1")
    monkeypatch.setenv("TESSERACT_BRIDGE_TEST_PANEL_PORT", "8123")
    monkeypatch.setenv("TESSERACT_BRIDGE_PANEL_PORT", "8999")
    result = load_runtime_config()
    assert result.backend == "simulated"
    assert result.mqtt.enabled is False
    assert result.panel.host == "127.0.0.1"
    assert result.panel.port == 8123
    assert store.load_config()["backend"] == "real"
    assert store.load_config()["mqtt"]["enabled"] is True


def test_normal_panel_port_is_process_only(monkeypatch):
    monkeypatch.setenv("TESSERACT_BRIDGE_SIMULATION_ONLY", "0")
    monkeypatch.setenv("TESSERACT_BRIDGE_PANEL_PORT", "8888")
    monkeypatch.setenv("TESSERACT_BRIDGE_PANEL_HOST", "127.0.0.1")
    loaded = load_runtime_config()
    assert loaded.panel.port == 8888
    assert loaded.panel.host == "127.0.0.1"
    assert store.load_config()["panel"]["port"] == 8088


@pytest.mark.parametrize("value", ["8090x", "-5", "0", "65536"])
def test_bad_port_is_rejected(value, monkeypatch):
    monkeypatch.setenv("TESSERACT_BRIDGE_TEST_PANEL_PORT", value)
    with pytest.raises(ValueError, match="porta"):
        port("TESSERACT_BRIDGE_TEST_PANEL_PORT")


def test_invalid_simulation_flag_fails_closed(monkeypatch):
    monkeypatch.setenv("TESSERACT_BRIDGE_SIMULATION_ONLY", "maybe")
    with pytest.raises(ValueError, match="TESSERACT_BRIDGE_SIMULATION_ONLY"):
        load_runtime_config()


def test_explicit_missing_sqlite_does_not_automatically_seed(tmp_path, monkeypatch):
    missing = tmp_path / "not-imported.sqlite3"
    monkeypatch.setenv("TESSERACT_BRIDGE_DB", str(missing))
    with pytest.raises(StorageError, match="inexistente"):
        load_runtime_config()
    assert not missing.exists()
