"""Verifica organização de pacotes sem inicializar GPIO físico."""
from importlib import import_module
from pathlib import Path

from tesseract_bridge.infrastructure.paths import DATA_DIR, PROJECT_ROOT
from tesseract_bridge.version import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]

MOVED = {
    "project_paths.py": "tesseract_bridge.infrastructure.paths",
    "infra_env.py": "tesseract_bridge.infrastructure.env",
    "python_runtime.py": "tesseract_bridge.infrastructure.python_runtime",
    "logging_config.py": "tesseract_bridge.infrastructure.logging_config",
    "failsafe_coercion.py": "tesseract_bridge.safety.failsafe_coercion",
    "failsafe_watchdog.py": "tesseract_bridge.safety.watchdog",
    "safety_lifecycle.py": "tesseract_bridge.safety.lifecycle",
    "source_control.py": "tesseract_bridge.control.source_control",
    "time_proportioning.py": "tesseract_bridge.control.time_proportioning",
    "remote_device_control.py": "tesseract_bridge.control.remote_device_control",
    "mqtt_client.py": "tesseract_bridge.integrations.mqtt_client",
    "status_handler.py": "tesseract_bridge.integrations.status_handler",
    "version.py": "tesseract_bridge.version",
}


def test_moved_modules_resolve_from_canonical_package():
    for legacy_name, qualified_name in MOVED.items():
        assert not (ROOT / legacy_name).exists(), legacy_name
        module = import_module(qualified_name)
        assert Path(module.__file__).resolve().is_relative_to(ROOT / "tesseract_bridge")


def test_entrypoints_remain_in_root_and_version_remains_v2():
    assert (ROOT / "run_bridge.py").is_file()
    assert (ROOT / "run_panel.py").is_file()
    assert APP_VERSION == "2.0.0"


def test_paths_remain_root_relative_even_after_code_move():
    assert PROJECT_ROOT == ROOT
    assert DATA_DIR == ROOT / "data"
