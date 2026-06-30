import textwrap

import pytest

from config import BridgeConfig
from recipe_engine.models import Recipe, RecipeError


DEVICES_YAML = """
mqtt:
  enabled: false
backend: simulated
panel:
  enabled: false

devices:
  - id: mash_tun_temp
    name: "Temp Mostura"
    role: sensor
    subtype: temperature
    state_topic: "sensors/mash_tun_temp/state"
    hardware: { pin: 4, driver: ds18b20, address: "28-aaa" }
    simulated: { initial_value: 25.0 }

  - id: boil_temp
    name: "Temp Fervura"
    role: sensor
    subtype: temperature
    state_topic: "sensors/boil_temp/state"
    hardware: { pin: 4, driver: ds18b20, address: "28-bbb" }
    simulated: { initial_value: 20.0 }

  - id: mash_heater
    name: "Aquecedor Mostura"
    role: actuator
    subtype: digital
    command_topic: "actuators/mash_heater/set"
    hardware: { pin: 17 }
    failsafe_value: false
    is_risk: true

  - id: boil_heater
    name: "Aquecedor Fervura"
    role: actuator
    subtype: digital
    command_topic: "actuators/boil_heater/set"
    hardware: { pin: 27 }
    failsafe_value: false
    is_risk: true

  - id: pump_b1
    name: "Bomba B1"
    role: actuator
    subtype: digital
    command_topic: "actuators/pump_b1/set"
    hardware: { pin: 22 }
    failsafe_value: false
    is_risk: true
"""


VALID_RECIPE_YAML = """
name: "Pilsen Clássica"
vessels:
  mash:
    heater_device_id: mash_heater
    sensor_device_id: mash_tun_temp
    pid: { kp: 5.0, ki: 0.1, kd: 0.0 }
    window_seconds: 10
  boil:
    heater_device_id: boil_heater
    sensor_device_id: boil_temp
    pid: { kp: 4.0, ki: 0.05, kd: 0.0 }
steps:
  - vessel: mash
    target_temp: 67
    hold_minutes: 60
    pumps: [pump_b1]
  - vessel: boil
    target_temp: 100
    hold_minutes: 60
"""


@pytest.fixture
def bridge_config(tmp_path):
    path = tmp_path / "devices.yml"
    path.write_text(textwrap.dedent(DEVICES_YAML), encoding="utf-8")
    return BridgeConfig.load(path)


def write_recipe(tmp_path, content: str):
    path = tmp_path / "recipe.yml"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def test_load_valid_recipe(tmp_path, bridge_config):
    path = write_recipe(tmp_path, VALID_RECIPE_YAML)
    recipe = Recipe.load(path, bridge_config)
    assert recipe.name == "Pilsen Clássica"
    assert recipe.step_count() == 2
    assert recipe.vessels["mash"].window_seconds == 10.0
    assert recipe.vessels["boil"].window_seconds == 10.0  # default


def test_missing_file_raises_recipe_error(tmp_path, bridge_config):
    with pytest.raises(RecipeError, match="não encontrado"):
        Recipe.load(tmp_path / "does_not_exist.yml", bridge_config)


def test_recipe_without_name_raises(tmp_path, bridge_config):
    content = "vessels: {}\nsteps: []\n"
    path = write_recipe(tmp_path, content)
    with pytest.raises(RecipeError, match="name"):
        Recipe.load(path, bridge_config)


def test_recipe_without_vessels_raises(tmp_path, bridge_config):
    content = 'name: "X"\nvessels: {}\nsteps: [{"vessel": "mash", "target_temp": 1, "hold_minutes": 1}]\n'
    path = write_recipe(tmp_path, content)
    with pytest.raises(RecipeError, match="ao menos uma vessel"):
        Recipe.load(path, bridge_config)


def test_recipe_without_steps_raises(tmp_path, bridge_config):
    content = """
    name: "X"
    vessels:
      mash:
        heater_device_id: mash_heater
        sensor_device_id: mash_tun_temp
        pid: { kp: 1, ki: 0, kd: 0 }
    steps: []
    """
    path = write_recipe(tmp_path, content)
    with pytest.raises(RecipeError, match="ao menos um step"):
        Recipe.load(path, bridge_config)


def test_vessel_referencing_unknown_heater_raises(tmp_path, bridge_config):
    content = """
    name: "X"
    vessels:
      mash:
        heater_device_id: does_not_exist
        sensor_device_id: mash_tun_temp
        pid: { kp: 1, ki: 0, kd: 0 }
    steps:
      - vessel: mash
        target_temp: 67
        hold_minutes: 10
    """
    path = write_recipe(tmp_path, content)
    with pytest.raises(RecipeError, match="heater_device_id 'does_not_exist'"):
        Recipe.load(path, bridge_config)


def test_step_referencing_unknown_vessel_raises(tmp_path, bridge_config):
    content = """
    name: "X"
    vessels:
      mash:
        heater_device_id: mash_heater
        sensor_device_id: mash_tun_temp
        pid: { kp: 1, ki: 0, kd: 0 }
    steps:
      - vessel: fervura_nao_declarada
        target_temp: 67
        hold_minutes: 10
    """
    path = write_recipe(tmp_path, content)
    with pytest.raises(RecipeError, match="vessel 'fervura_nao_declarada' não declarada"):
        Recipe.load(path, bridge_config)


def test_step_referencing_unknown_pump_raises(tmp_path, bridge_config):
    content = """
    name: "X"
    vessels:
      mash:
        heater_device_id: mash_heater
        sensor_device_id: mash_tun_temp
        pid: { kp: 1, ki: 0, kd: 0 }
    steps:
      - vessel: mash
        target_temp: 67
        hold_minutes: 10
        pumps: [bomba_inexistente]
    """
    path = write_recipe(tmp_path, content)
    with pytest.raises(RecipeError, match="pump 'bomba_inexistente'"):
        Recipe.load(path, bridge_config)


def test_negative_hold_minutes_raises(tmp_path, bridge_config):
    content = """
    name: "X"
    vessels:
      mash:
        heater_device_id: mash_heater
        sensor_device_id: mash_tun_temp
        pid: { kp: 1, ki: 0, kd: 0 }
    steps:
      - vessel: mash
        target_temp: 67
        hold_minutes: -5
    """
    path = write_recipe(tmp_path, content)
    with pytest.raises(RecipeError, match="hold_minutes não pode ser negativo"):
        Recipe.load(path, bridge_config)


def test_pid_missing_field_raises(tmp_path, bridge_config):
    content = """
    name: "X"
    vessels:
      mash:
        heater_device_id: mash_heater
        sensor_device_id: mash_tun_temp
        pid: { kp: 1, ki: 0 }
    steps:
      - vessel: mash
        target_temp: 67
        hold_minutes: 10
    """
    path = write_recipe(tmp_path, content)
    with pytest.raises(RecipeError, match="pid sem campo"):
        Recipe.load(path, bridge_config)
