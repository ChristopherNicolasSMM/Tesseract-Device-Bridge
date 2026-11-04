"""Cross-domain validation independent of SQLAlchemy and Flask.

The same rules are used by the administrative API and ORM store so a
configuration cannot be approved through one path but rejected by another.
"""
from __future__ import annotations

from config import BridgeConfig
from recipe_engine.models import Recipe, RecipeError


def validate_recipe_document(payload, bridge_config):
    recipe = Recipe.from_dict(payload)
    recipe.validate(bridge_config)
    return recipe


def validate_configuration_document(payload, recipes, calibrations):
    """Validate configuration and every dependent recipe/calibration.

    recipes: iterable of (recipe_id, Python recipe dict).
    calibrations: mapping sensor_id -> {address, offset_c}.
    No persistence side effects.
    """
    cfg = BridgeConfig.from_dict(payload)
    cfg.validate()
    for recipe_id, raw in recipes:
        try:
            validate_recipe_document(raw, cfg)
        except (RecipeError, ValueError, TypeError) as exc:
            raise ValueError(
                f"Dispositivo incompatível com receita {recipe_id}: {exc}"
            ) from exc
    for sensor_id, entry in calibrations.items():
        sensor = next((d for d in cfg.devices if d.id == sensor_id), None)
        if sensor is None or sensor.hardware.get("address") != entry["address"]:
            raise ValueError(
                f"Calibração de {sensor_id} incompatível com nova configuração/ROM ID."
            )
    return cfg
