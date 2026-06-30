import textwrap

import pytest

from config import BridgeConfig
from device_runtime import DeviceRuntime
from gpio.simulated_backend import SimulatedGPIOBackend
from panel.app import create_panel_app
 

YAML_CONTENT = """
mqtt:
  enabled: false
backend: simulated
panel:
  enabled: true

devices:
  - id: mash_tun_temp
    name: "Temperatura Mostura"
    role: sensor
    subtype: temperature
    unit: "°C"
    state_topic: "sensors/mash_tun_temp/state"
    hardware:
      pin: 4
    simulated:
      initial_value: 25.0
      min: 0
      max: 120

  - id: mash_heater
    name: "Resistencia Mostura"
    role: actuator
    subtype: pwm
    unit: "%"
    command_topic: "actuators/mash_heater/set"
    hardware:
      pin: 18
    failsafe_value: 0
    is_risk: true
    failsafe_timeout_seconds: 30
    limits:
      min: 0
      max: 100
"""


@pytest.fixture
def client(tmp_path):
    path = tmp_path / "devices.yml"
    path.write_text(textwrap.dedent(YAML_CONTENT), encoding="utf-8")
    config = BridgeConfig.load(path)
    backend = SimulatedGPIOBackend()
    runtime = DeviceRuntime(config, backend)
    app = create_panel_app(config, runtime)
    app.testing = True
    return app.test_client()


def test_index_page_loads(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"Tesseract Device Bridge" in res.data


def test_status_reports_disabled_when_mqtt_disabled(client):
    res = client.get("/api/status")
    assert res.status_code == 200
    assert res.get_json() == {"mqtt": "disabled"}


def test_list_devices_returns_both_devices(client):
    res = client.get("/api/devices")
    assert res.status_code == 200
    data = res.get_json()
    ids = {d["id"] for d in data}
    assert ids == {"mash_tun_temp", "mash_heater"}


def test_list_devices_includes_range(client):
    res = client.get("/api/devices")
    data = res.get_json()
    sensor = next(d for d in data if d["id"] == "mash_tun_temp")
    assert sensor["range"] == {"min": 0, "max": 120}
    
    
def test_list_devices_includes_gpio_pin(client):
    res = client.get("/api/devices")
    data = res.get_json()
    sensor = next(d for d in data if d["id"] == "mash_tun_temp")
    actuator = next(d for d in data if d["id"] == "mash_heater")
    assert sensor["gpio"] == 4
    assert actuator["gpio"] == 18    


def test_get_single_device(client):
    res = client.get("/api/devices/mash_tun_temp")
    assert res.status_code == 200
    assert res.get_json()["value"] == 25.0


def test_get_unknown_device_returns_404(client):
    res = client.get("/api/devices/does_not_exist")
    assert res.status_code == 404


def test_command_actuator_updates_value(client):
    res = client.post("/api/devices/mash_heater/command", json={"value": 75.0})
    assert res.status_code == 200
    assert res.get_json()["value"] == 75.0

    res2 = client.get("/api/devices/mash_heater")
    assert res2.get_json()["value"] == 75.0


def test_command_without_value_returns_400(client):
    res = client.post("/api/devices/mash_heater/command", json={})
    assert res.status_code == 400


def test_command_on_sensor_returns_400(client):
    res = client.post("/api/devices/mash_tun_temp/command", json={"value": 1})
    assert res.status_code == 400


def test_command_unknown_device_returns_404(client):
    res = client.post("/api/devices/does_not_exist/command", json={"value": 1})
    assert res.status_code == 404


def test_simulate_sensor_updates_value(client):
    res = client.post("/api/devices/mash_tun_temp/simulate", json={"value": 99.0})
    assert res.status_code == 200
    assert res.get_json()["value"] == 99.0


def test_simulate_without_value_returns_400(client):
    res = client.post("/api/devices/mash_tun_temp/simulate", json={})
    assert res.status_code == 400


def test_simulate_on_actuator_returns_400(client):
    res = client.post("/api/devices/mash_heater/simulate", json={"value": 1})
    assert res.status_code == 400


def test_simulate_unknown_device_returns_404(client):
    res = client.post("/api/devices/does_not_exist/simulate", json={"value": 1})
    assert res.status_code == 404


def test_recipe_status_returns_404_when_no_recipe_engine(client):
    res = client.get("/api/recipe/status")
    assert res.status_code == 404


def test_recipe_start_returns_404_when_no_recipe_engine(client):
    res = client.post("/api/recipe/start")
    assert res.status_code == 404


@pytest.fixture
def client_with_recipe(tmp_path):
    from config import BridgeConfig
    from device_runtime import DeviceRuntime
    from gpio.simulated_backend import SimulatedGPIOBackend
    from recipe_engine.engine import RecipeEngine
    from recipe_engine.models import Recipe

    devices_path = tmp_path / "devices.yml"
    devices_path.write_text(textwrap.dedent(YAML_CONTENT), encoding="utf-8")
    config = BridgeConfig.load(devices_path)
    backend = SimulatedGPIOBackend()
    runtime = DeviceRuntime(config, backend)

    recipe_yaml = """
    name: "Receita Teste Painel"
    vessels:
      mash:
        heater_device_id: mash_heater
        sensor_device_id: mash_tun_temp
        pid: { kp: 50.0, ki: 0.0, kd: 0.0 }
        window_seconds: 10
    steps:
      - vessel: mash
        target_temp: 35.0
        hold_minutes: 1
    """
    recipe_path = tmp_path / "recipe.yml"
    recipe_path.write_text(textwrap.dedent(recipe_yaml), encoding="utf-8")
    recipe = Recipe.load(recipe_path, config)
    state_path = tmp_path / "recipe_state.json"
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)

    app = create_panel_app(config, runtime, recipe_engine=engine)
    app.testing = True
    return app.test_client(), engine


def test_recipe_status_returns_idle_initially(client_with_recipe):
    client, engine = client_with_recipe
    res = client.get("/api/recipe/status")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "idle"
    assert data["loaded_recipe_name"] == "Receita Teste Painel"


def test_recipe_start_transitions_to_ramping(client_with_recipe):
    client, engine = client_with_recipe
    res = client.post("/api/recipe/start")
    assert res.status_code == 200
    assert res.get_json()["status"] == "ramping"


def test_recipe_status_includes_current_vessel_and_duty(client_with_recipe):
    client, engine = client_with_recipe
    client.post("/api/recipe/start")
    engine.tick(now=1000.0)
    engine.tick(now=1001.0)

    res = client.get("/api/recipe/status")
    data = res.get_json()
    assert data["current_vessel"] == "mash"
    assert data["current_duty_percent"] > 0


def test_recipe_abort_sets_aborted(client_with_recipe):
    client, engine = client_with_recipe
    client.post("/api/recipe/start")
    res = client.post("/api/recipe/abort")
    assert res.status_code == 200
    assert res.get_json()["status"] == "aborted"


def test_recipe_resume_without_crash_returns_400(client_with_recipe):
    client, engine = client_with_recipe
    res = client.post("/api/recipe/resume")
    assert res.status_code == 400


def test_recipe_definition_returns_vessels_and_steps(client_with_recipe):
    client, engine = client_with_recipe
    res = client.get("/api/recipe/definition")
    assert res.status_code == 200
    data = res.get_json()
    assert data["name"] == "Receita Teste Painel"
    assert "mash" in data["vessels"]
    assert data["vessels"]["mash"]["heater_device_id"] == "mash_heater"
    assert len(data["steps"]) == 1
    assert data["steps"][0]["target_temp"] == 35.0


def test_recipe_definition_returns_404_when_no_recipe_engine(client):
    res = client.get("/api/recipe/definition")
    assert res.status_code == 404
