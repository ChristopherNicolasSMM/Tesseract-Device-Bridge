"""Version 2.0.0 documentation and UI identification regression."""
from pathlib import Path

from config import BridgeConfig
from device_runtime import DeviceRuntime
from gpio.simulated_backend import SimulatedGPIOBackend
from panel.app import create_panel_app
from storage import sqlite_store as store
from tesseract_bridge.version import APP_VERSION


def test_version_is_2_0_0():
    assert APP_VERSION == "2.0.0"


def test_local_panel_displays_version_in_title_and_header():
    config = BridgeConfig.from_dict(store.load_config())
    config.validate()
    runtime = DeviceRuntime(config, SimulatedGPIOBackend())
    try:
        app = create_panel_app(config, runtime)
        response = app.test_client().get("/")
        assert response.status_code == 200
        assert b"v2.0.0" in response.data
    finally:
        runtime.shutdown()


def test_release_docs_include_migration_and_admin_manual():
    root = Path(__file__).resolve().parents[1]
    assert (root / "docs/manual/13-administracao-sqlite.md").exists()
    assert (root / "CHANGELOG.md").exists()
    intro = (root / "docs/manual/01-introducao.md").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "2.0.0" in intro
    assert "Administração SQLite" in readme
