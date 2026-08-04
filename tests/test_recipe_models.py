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
    hardware: { pin: 17, window_seconds: 10 }
    failsafe_value: false
    is_risk: true

  - id: boil_heater
    name: "Aquecedor Fervura"
    role: actuator
    subtype: digital
    command_topic: "actuators/boil_heater/set"
    hardware: { pin: 27, window_seconds: 10 }
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
  - id: mash
    name: "Mash"
    heater_device_id: mash_heater
    sensor_device_id: mash_tun_temp
    pid: { kp: 5.0, ki: 0.1, kd: 0.0 }
  - id: boil
    name: "Boil"
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
    # window_seconds nao existe mais em VesselConfig -- fonte de verdade
    # e hardware.window_seconds no devices.yml do heater_device_id.
    assert bridge_config.get_device("mash_heater").hardware["window_seconds"] == 10
    assert bridge_config.get_device("boil_heater").hardware["window_seconds"] == 10


def test_vessel_config_no_longer_has_window_seconds_field(tmp_path, bridge_config):
    path = write_recipe(tmp_path, VALID_RECIPE_YAML)
    recipe = Recipe.load(path, bridge_config)
    assert not hasattr(recipe.get_vessel("mash"), "window_seconds")


def test_recipe_yaml_with_deprecated_window_seconds_warns_and_is_ignored(tmp_path, bridge_config):
    content = VALID_RECIPE_YAML.replace(
        'pid: { kp: 5.0, ki: 0.1, kd: 0.0 }',
        'pid: { kp: 5.0, ki: 0.1, kd: 0.0 }\n    window_seconds: 99',
    )
    path = write_recipe(tmp_path, content)
    with pytest.warns(DeprecationWarning, match="obsoleto"):
        recipe = Recipe.load(path, bridge_config)
    assert not hasattr(recipe.get_vessel("mash"), "window_seconds")


def test_heater_without_window_seconds_raises(tmp_path, bridge_config):
    # mash_tun_temp nao tem window_seconds -- usar como heater deve falhar cedo
    content = VALID_RECIPE_YAML.replace(
        "heater_device_id: mash_heater", "heater_device_id: mash_tun_temp"
    )
    path = write_recipe(tmp_path, content)
    with pytest.raises(RecipeError, match="hardware.window_seconds"):
        Recipe.load(path, bridge_config)


def test_missing_file_raises_recipe_error(tmp_path, bridge_config):
    with pytest.raises(RecipeError, match="não encontrado"):
        Recipe.load(tmp_path / "does_not_exist.yml", bridge_config)


def test_recipe_without_name_raises(tmp_path, bridge_config):
    content = "vessels: []\nsteps: []\n"
    path = write_recipe(tmp_path, content)
    with pytest.raises(RecipeError, match="name"):
        Recipe.load(path, bridge_config)


def test_recipe_without_vessels_raises(tmp_path, bridge_config):
    content = 'name: "X"\nvessels: []\nsteps: [{"vessel": "mash", "target_temp": 1, "hold_minutes": 1}]\n'
    path = write_recipe(tmp_path, content)
    with pytest.raises(RecipeError, match="ao menos uma vessel"):
        Recipe.load(path, bridge_config)


def test_recipe_without_steps_raises(tmp_path, bridge_config):
    content = """
    name: "X"
    vessels:
      - id: mash
        name: "Mash"
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
      - id: mash
        name: "Mash"
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
      - id: mash
        name: "Mash"
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
      - id: mash
        name: "Mash"
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
      - id: mash
        name: "Mash"
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
      - id: mash
        name: "Mash"
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


def test_vessel_without_name_raises_clean_recipe_error(tmp_path, bridge_config):
    """
    Regressão: campo obrigatório ausente (agora `name`, antes era
    `label`) deve estourar RecipeError explicando o que falta, nunca
    KeyError cru.
    """
    content = """
    name: "X"
    vessels:
      - id: mash
        heater_device_id: mash_heater
        sensor_device_id: mash_tun_temp
        pid: { kp: 1, ki: 0, kd: 0 }
    steps:
      - vessel: mash
        target_temp: 67
        hold_minutes: 10
    """
    path = write_recipe(tmp_path, content)
    with pytest.raises(RecipeError, match=r"campo\(s\) obrigatório\(s\) ausente\(s\) \['name'\]"):
        Recipe.load(path, bridge_config)


def test_vessel_without_id_raises_clean_recipe_error(tmp_path, bridge_config):
    content = """
    name: "X"
    vessels:
      - name: "Mash"
        heater_device_id: mash_heater
        sensor_device_id: mash_tun_temp
        pid: { kp: 1, ki: 0, kd: 0 }
    steps:
      - vessel: mash
        target_temp: 67
        hold_minutes: 10
    """
    path = write_recipe(tmp_path, content)
    with pytest.raises(RecipeError, match=r"campo\(s\) obrigatório\(s\) ausente\(s\) \['id'\]"):
        Recipe.load(path, bridge_config)


def test_duplicate_vessel_id_raises(tmp_path, bridge_config):
    content = """
    name: "X"
    vessels:
      - id: mash
        name: "Mash 1"
        heater_device_id: mash_heater
        sensor_device_id: mash_tun_temp
        pid: { kp: 1, ki: 0, kd: 0 }
      - id: mash
        name: "Mash 2"
        heater_device_id: boil_heater
        sensor_device_id: boil_temp
        pid: { kp: 1, ki: 0, kd: 0 }
    steps:
      - vessel: mash
        target_temp: 67
        hold_minutes: 10
    """
    path = write_recipe(tmp_path, content)
    with pytest.raises(RecipeError, match="id de vessel duplicado: 'mash'"):
        Recipe.load(path, bridge_config)


def test_vessel_order_explicit_is_respected(tmp_path, bridge_config):
    content = """
    name: "X"
    vessels:
      - id: boil
        name: "Fervura"
        heater_device_id: boil_heater
        sensor_device_id: boil_temp
        pid: { kp: 1, ki: 0, kd: 0 }
        order: 1
      - id: mash
        name: "Mostura"
        heater_device_id: mash_heater
        sensor_device_id: mash_tun_temp
        pid: { kp: 1, ki: 0, kd: 0 }
        order: 0
    steps:
      - vessel: mash
        target_temp: 67
        hold_minutes: 10
    """
    path = write_recipe(tmp_path, content)
    recipe = Recipe.load(path, bridge_config)
    # Apesar de "boil" vir primeiro no YAML, order explícito o coloca depois.
    assert recipe.ordered_vessel_names() == ["mash", "boil"]


def test_vessel_order_defaults_to_declaration_order(tmp_path, bridge_config):
    content = """
    name: "X"
    vessels:
      - id: boil
        name: "Fervura"
        heater_device_id: boil_heater
        sensor_device_id: boil_temp
        pid: { kp: 1, ki: 0, kd: 0 }
      - id: mash
        name: "Mostura"
        heater_device_id: mash_heater
        sensor_device_id: mash_tun_temp
        pid: { kp: 1, ki: 0, kd: 0 }
    steps:
      - vessel: mash
        target_temp: 67
        hold_minutes: 10
    """
    path = write_recipe(tmp_path, content)
    recipe = Recipe.load(path, bridge_config)
    # Sem order explícito, mantém a ordem de declaração no YAML (boil primeiro).
    assert recipe.ordered_vessel_names() == ["boil", "mash"]


def test_get_vessel_unknown_id_raises(tmp_path, bridge_config):
    path = write_recipe(tmp_path, VALID_RECIPE_YAML)
    recipe = Recipe.load(path, bridge_config)
    with pytest.raises(RecipeError, match="não existe nesta receita"):
        recipe.get_vessel("does_not_exist")


def test_step_with_hop_alarms_loads_correctly(tmp_path, bridge_config):
    content = """
    name: "X"
    vessels:
      - id: boil
        name: "Fervura"
        heater_device_id: boil_heater
        sensor_device_id: boil_temp
        pid: { kp: 1, ki: 0, kd: 0 }
    steps:
      - vessel: boil
        target_temp: 100
        hold_minutes: 60
        hop_alarms:
          - minutes_remaining: 60
            label: "5kg Lupulo Amargor"
          - minutes_remaining: 15
            label: "2kg Lupulo Aroma"
          - minutes_remaining: 0
            label: "Whirlpool"
    """
    path = write_recipe(tmp_path, content)
    recipe = Recipe.load(path, bridge_config)
    alarms = recipe.steps[0].hop_alarms
    assert len(alarms) == 3
    assert alarms[0].minutes_remaining == 60.0
    assert alarms[0].label == "5kg Lupulo Amargor"
    assert alarms[2].minutes_remaining == 0.0


def test_step_without_hop_alarms_defaults_to_empty_list(tmp_path, bridge_config):
    path = write_recipe(tmp_path, VALID_RECIPE_YAML)
    recipe = Recipe.load(path, bridge_config)
    assert recipe.steps[0].hop_alarms == []


def test_hop_alarm_missing_label_raises(tmp_path, bridge_config):
    content = """
    name: "X"
    vessels:
      - id: boil
        name: "Fervura"
        heater_device_id: boil_heater
        sensor_device_id: boil_temp
        pid: { kp: 1, ki: 0, kd: 0 }
    steps:
      - vessel: boil
        target_temp: 100
        hold_minutes: 60
        hop_alarms:
          - minutes_remaining: 60
    """
    path = write_recipe(tmp_path, content)
    with pytest.raises(RecipeError, match=r"campo\(s\) obrigatório\(s\) ausente\(s\) \['label'\]"):
        Recipe.load(path, bridge_config)


def test_hop_alarm_negative_minutes_raises(tmp_path, bridge_config):
    content = """
    name: "X"
    vessels:
      - id: boil
        name: "Fervura"
        heater_device_id: boil_heater
        sensor_device_id: boil_temp
        pid: { kp: 1, ki: 0, kd: 0 }
    steps:
      - vessel: boil
        target_temp: 100
        hold_minutes: 60
        hop_alarms:
          - minutes_remaining: -5
            label: "Invalido"
    """
    path = write_recipe(tmp_path, content)
    with pytest.raises(RecipeError, match="não pode ser negativo"):
        Recipe.load(path, bridge_config)


def test_hop_alarm_minutes_greater_than_hold_raises(tmp_path, bridge_config):
    content = """
    name: "X"
    vessels:
      - id: boil
        name: "Fervura"
        heater_device_id: boil_heater
        sensor_device_id: boil_temp
        pid: { kp: 1, ki: 0, kd: 0 }
    steps:
      - vessel: boil
        target_temp: 100
        hold_minutes: 60
        hop_alarms:
          - minutes_remaining: 90
            label: "Nunca vai disparar"
    """
    path = write_recipe(tmp_path, content)
    with pytest.raises(RecipeError, match="nunca dispararia"):
        Recipe.load(path, bridge_config)
