"""Regressão da calibração por sensor, sem acesso a GPIO real."""
import math
import pytest

from config import BridgeConfig
from device_runtime import DeviceRuntime
from gpio.simulated_backend import SimulatedGPIOBackend
from panel.app import create_panel_app
from temperature_calibration import load_calibrations, save_calibrations


def make_config():
    config = BridgeConfig.from_dict({
        "mqtt": {"enabled": False}, "backend": "simulated", "panel": {"enabled": True},
        "devices": [
            {"id": "mash_temp", "name": "Mostura", "role": "sensor",
             "subtype": "temperature", "state_topic": "sensors/mash/state",
             "hardware": {"pin": 4, "address": "28-aaa", "driver": "ds18b20"},
             "simulated": {"initial_value": 64.9}},
            {"id": "boil_temp", "name": "Fervura", "role": "sensor",
             "subtype": "temperature", "state_topic": "sensors/boil/state",
             "hardware": {"pin": 4, "address": "28-bbb", "driver": "ds18b20"},
             "simulated": {"initial_value": 99.0}},
            {"id": "heater", "name": "Resistência", "role": "actuator",
             "subtype": "digital", "command_topic": "actuators/heater/set",
             "hardware": {"pin": 12, "window_seconds": 5},
             "failsafe_value": False, "is_risk": True},
        ],
    })
    config.validate()
    return config


def payload(mash=2.1, boil=0.0):
    return {"schema": 1, "sensors": {
        "mash_temp": {"address": "28-aaa", "offset_c": mash},
        "boil_temp": {"address": "28-bbb", "offset_c": boil},
    }}


def test_calibration_per_sensor_preserves_raw_and_controls_corrected(tmp_path):
    config = make_config()
    path = tmp_path / "private" / "sensor_calibration.json"
    save_calibrations(payload(2.1, -0.5), config.devices, path)
    backend = SimulatedGPIOBackend()
    runtime = DeviceRuntime(config, backend, calibration_path=path)
    mash = runtime.get_state("mash_temp")
    boil = runtime.get_state("boil_temp")
    assert mash.raw_value == pytest.approx(64.9)
    assert mash.value == pytest.approx(67.0)
    assert mash.temperature_offset_c == pytest.approx(2.1)
    assert boil.value == pytest.approx(98.5)
    runtime.inject_sensor("mash_temp", 66.0)
    assert runtime.get_state("mash_temp").value == pytest.approx(68.1)
    assert runtime.get_state("heater").raw_value is None
    runtime.shutdown()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -5.1, 5.1, True, "2.1"])
def test_reject_invalid_offsets_without_persisting(tmp_path, value):
    config = make_config()
    path = tmp_path / "sensor_calibration.json"
    with pytest.raises(ValueError):
        save_calibrations(payload(value), config.devices, path)
    assert not path.exists()


def test_reject_changed_rom_and_unknown_device(tmp_path):
    config = make_config()
    path = tmp_path / "private" / "sensor_calibration.json"
    saved = payload()
    saved["sensors"]["mash_temp"]["address"] = "28-other"
    with pytest.raises(ValueError, match="endereço físico mudou"):
        save_calibrations(saved, config.devices, path)
    save_calibrations(payload(), config.devices, path)
    config.get_device("mash_temp").hardware["address"] = "28-replaced"
    with pytest.raises(ValueError, match="recalibre"):
        DeviceRuntime(config, SimulatedGPIOBackend(), calibration_path=path)


def test_http_save_only_applies_after_new_runtime(tmp_path):
    config = make_config()
    path = tmp_path / "private" / "sensor_calibration.json"
    runtime = DeviceRuntime(config, SimulatedGPIOBackend(), calibration_path=path)
    app = create_panel_app(config, runtime)
    client = app.test_client()
    first = client.get("/api/sensor-calibration")
    assert first.status_code == 200
    assert len(first.json["sensors"]) == 2
    assert first.json["sensors"][0]["active_offset_c"] == 0
    saved = client.put("/api/sensor-calibration", json=payload())
    assert saved.status_code == 200
    assert saved.json["restart_required"] is True
    assert runtime.get_state("mash_temp").value == pytest.approx(64.9)
    pending = client.get("/api/sensor-calibration").json["sensors"]
    assert next(s for s in pending if s["id"] == "mash_temp")["pending_restart"]
    runtime.shutdown()
    restarted = DeviceRuntime(config, SimulatedGPIOBackend(), calibration_path=path)
    assert restarted.get_state("mash_temp").value == pytest.approx(67.0)
    restarted.shutdown()


def test_http_rejects_bad_payload(tmp_path):
    config = make_config()
    runtime = DeviceRuntime(config, SimulatedGPIOBackend(),
                            calibration_path=tmp_path / "calibration.json")
    app = create_panel_app(config, runtime)
    result = app.test_client().put("/api/sensor-calibration", json={"schema": 1, "sensors": {
        "mash_temp": {"address": "28-aaa", "offset_c": 9.0}}})
    assert result.status_code == 400
    runtime.shutdown()



def test_http_rejects_save_while_recipe_is_running(tmp_path):
    from types import SimpleNamespace

    config = make_config()
    path = tmp_path / "calibration.json"
    runtime = DeviceRuntime(config, SimulatedGPIOBackend(), calibration_path=path)
    app = create_panel_app(config, runtime)
    app.config["RECIPE_ENGINE"] = SimpleNamespace(state=SimpleNamespace(status="ramping"))
    res = app.test_client().put("/api/sensor-calibration", json=payload())
    assert res.status_code == 409
    assert not path.exists()
    runtime.shutdown()
