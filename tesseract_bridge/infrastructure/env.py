"""Runtime infrastructure settings loaded from the project-local .env.

Only the process environment is changed; the SQLite contents remain untouched.
Explicit shell/service environment variables always take precedence over .env.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from tesseract_bridge.infrastructure.paths import PROJECT_ROOT

DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"


def load_infra_env(path=None):
    """Load only this installation's .env, never an ancestor or caller CWD."""
    target = Path(path) if path is not None else DEFAULT_ENV_FILE
    if not target.is_file():
        return False
    return bool(load_dotenv(dotenv_path=target, override=False, encoding="utf-8"))


def flag(name, default=False):
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    value = value.strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    raise ValueError(
        f"{name} inválido: esperado 1/0, true/false, yes/no ou on/off."
    )


def port(name, default=None):
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"{name} inválido: porta deve ser número inteiro.") from exc
    if not 1 <= value <= 65535:
        raise ValueError(f"{name} inválido: porta entre 1 e 65535.")
    return value
