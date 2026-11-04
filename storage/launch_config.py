"""Load an approved SQLite snapshot with optional process-only infra overrides.

Settings are never saved back to the database by this module. The simulation
flag disables physical GPIO and MQTT for a safe, isolated test clone.
"""
from __future__ import annotations

import copy
import os

from config import BridgeConfig
from tesseract_bridge.infrastructure.env import flag, load_infra_env, port
from storage import sqlite_store as store
from storage.migrate import StorageError


def load_runtime_config():
    load_infra_env()
    selected = os.environ.get("TESSERACT_BRIDGE_DB")
    if selected and not store.db_path().is_file():
        raise StorageError(
            f"TESSERACT_BRIDGE_DB aponta para banco inexistente: {store.db_path()}. "
            "Importe os dados legados ou inicialize explicitamente com "
            "'python -m storage.cli init'."
        )
    store.initialize(seed=True)
    raw = store.load_config()
    if flag("TESSERACT_BRIDGE_SIMULATION_ONLY", False):
        # Process-local override; neither SQLite nor approved GPIO config changes.
        raw = copy.deepcopy(raw)
        raw["backend"] = "simulated"
        raw["mqtt"]["enabled"] = False
        raw["panel"]["enabled"] = True
        raw["panel"]["host"] = "127.0.0.1"
        raw["panel"]["port"] = port("TESSERACT_BRIDGE_TEST_PANEL_PORT", 8089)
    else:
        # Optional infrastructure-only bind override. Operational resources
        # (MQTT, GPIO, recipes, sensors, PID) still come from SQLite.
        custom_port = port("TESSERACT_BRIDGE_PANEL_PORT")
        if custom_port is not None:
            raw["panel"]["port"] = custom_port
        custom_host = os.environ.get("TESSERACT_BRIDGE_PANEL_HOST", "").strip()
        if custom_host:
            raw["panel"]["host"] = custom_host

    config = BridgeConfig.from_dict(raw)
    config.validate()
    return config
