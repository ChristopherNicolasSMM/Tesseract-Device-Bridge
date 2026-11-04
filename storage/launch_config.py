"""Load an approved SQLite config; optional no-hardware simulation in a separate clone."""
from __future__ import annotations
import copy
import os

from config import BridgeConfig
from storage import sqlite_store as store


def load_runtime_config():
    store.initialize(seed=True)
    raw = store.load_config()
    if os.environ.get("TESSERACT_BRIDGE_SIMULATION_ONLY") == "1":
        # Overrides are process-local; the imported SQLite snapshot remains intact.
        raw = copy.deepcopy(raw)
        raw["backend"] = "simulated"
        raw["mqtt"]["enabled"] = False
        raw["panel"]["enabled"] = True
        raw["panel"]["port"] = int(os.environ.get("TESSERACT_BRIDGE_TEST_PANEL_PORT", "8089"))
        # Local-only by default. Remote inspection needs an explicit host change.
        raw["panel"]["host"] = "127.0.0.1"
    config = BridgeConfig.from_dict(raw)
    config.validate()
    return config
