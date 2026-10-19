"""Default paths are relative to the installation, never to the caller's cwd.
Explicit user-supplied paths retain normal pathlib semantics.
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_CONFIG_PATH = DATA_DIR / "public" / "devices.yml"
EXAMPLE_CONFIG_PATH = DATA_DIR / "public" / "devices.yml.example"
DEFAULT_RECIPE_STATE_PATH = DATA_DIR / "private" / "recipe_state.json"
LEGACY_RECIPE_PATH = PROJECT_ROOT / "recipe.yml"
