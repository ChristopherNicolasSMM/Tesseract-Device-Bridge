"""Pure cross-domain validation, shared by the UI and ORM."""
import copy

import pytest

from storage import sqlite_store as store
from tesseract_bridge.services.validation import (
    validate_configuration_document, validate_recipe_document,
)


def test_recipe_validation_keeps_existing_domain_rules():
    from tests.test_data_store import config, recipe
    cfg = config()
    loaded = validate_recipe_document(recipe("Validated"), cfg)
    assert loaded.name == "Validated"


def test_configuration_rejects_orphaned_recipe_dependencies():
    from tests.test_data_store import config, recipe
    config()
    candidate = copy.deepcopy(store.load_config())
    invalid = recipe("Broken")
    invalid["vessels"][0]["heater_device_id"] = "not_available"
    with pytest.raises(ValueError, match="Dispositivo incompatível"):
        validate_configuration_document(
            candidate, [("private:broken", invalid)], {}
        )


def test_configuration_rejects_orphaned_calibration():
    from tests.test_data_store import config
    config()
    candidate = copy.deepcopy(store.load_config())
    with pytest.raises(ValueError, match="Calibração"):
        validate_configuration_document(
            candidate, [], {"missing_sensor": {"address": None, "offset_c": 0}}
        )
