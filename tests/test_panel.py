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
