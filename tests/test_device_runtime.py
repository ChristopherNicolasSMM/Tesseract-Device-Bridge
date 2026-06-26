import textwrap

import pytest

from config import BridgeConfig
from device_runtime import DeviceRuntime, DeviceRuntimeError, resolve_mode
from gpio.simulated_backend import SimulatedGPIOBackend


def make_config(tmp_path, content: str) -> BridgeConfig:
    path = tmp_path / "devices.yml"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return BridgeConfig.load(path)


YAML_BASIC = """
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

  - id: mash_heater
    name: "Resistencia Mostura"
    role: actuator
    subtype: pwm
    unit: "%"
    command_topic: "actuators/mash_heater/set"
    hardware:
      pin: 18
      pwm_frequency: 1000
    failsafe_value: 0
    is_risk: true
    failsafe_timeout_seconds: 30

  - id: mash_pump
    name: "Bomba Mostura"
    role: actuator
    subtype: digital
    command_topic: "actuators/mash_pump/set"
    hardware:
      pin: 20
    failsafe_value: false
    is_risk: true
    failsafe_timeout_seconds: 30
"""


def test_resolve_mode_sensor_temperature():
    assert resolve_mode("sensor", "temperature") == "input_analog"


def test_resolve_mode_actuator_pwm():
    assert resolve_mode("actuator", "pwm") == "pwm"


def test_resolve_mode_actuator_digital():
    assert resolve_mode("actuator", "digital") == "output"


def test_resolve_mode_unknown_subtype_falls_back_to_role_default():
    assert resolve_mode("sensor", "humidity") == "input"
    assert resolve_mode("actuator", "stepper") == "output"


def test_setup_all_configures_every_device_pin(tmp_path):
    config = make_config(tmp_path, YAML_BASIC)
    backend = SimulatedGPIOBackend()
    runtime = DeviceRuntime(config, backend)

    states = runtime.list_devices()
    assert len(states) == 3
    ids = {s.id for s in states}
    assert ids == {"mash_tun_temp", "mash_heater", "mash_pump"}


def test_sensor_initial_value_applied(tmp_path):
    config = make_config(tmp_path, YAML_BASIC)
    backend = SimulatedGPIOBackend()
    runtime = DeviceRuntime(config, backend)

    state = runtime.get_state("mash_tun_temp")
    assert state.value == 25.0
    assert state.unit == "°C"


def test_set_actuator_writes_value(tmp_path):
    config = make_config(tmp_path, YAML_BASIC)
    backend = SimulatedGPIOBackend()
    runtime = DeviceRuntime(config, backend)

    state = runtime.set_actuator("mash_heater", 60.0)
    assert state.value == 60.0
    assert runtime.get_state("mash_heater").value == 60.0


def test_set_actuator_on_sensor_raises(tmp_path):
    config = make_config(tmp_path, YAML_BASIC)
    backend = SimulatedGPIOBackend()
    runtime = DeviceRuntime(config, backend)

    with pytest.raises(DeviceRuntimeError):
        runtime.set_actuator("mash_tun_temp", 1.0)


def test_inject_sensor_updates_value(tmp_path):
    config = make_config(tmp_path, YAML_BASIC)
    backend = SimulatedGPIOBackend()
    runtime = DeviceRuntime(config, backend)

    state = runtime.inject_sensor("mash_tun_temp", 80.0)
    assert state.value == 80.0


def test_inject_sensor_on_actuator_raises(tmp_path):
    config = make_config(tmp_path, YAML_BASIC)
    backend = SimulatedGPIOBackend()
    runtime = DeviceRuntime(config, backend)

    with pytest.raises(DeviceRuntimeError):
        runtime.inject_sensor("mash_heater", 1.0)


def test_apply_failsafe_sets_failsafe_value(tmp_path):
    config = make_config(tmp_path, YAML_BASIC)
    backend = SimulatedGPIOBackend()
    runtime = DeviceRuntime(config, backend)

    runtime.set_actuator("mash_pump", True)
    assert runtime.get_state("mash_pump").value is True

    state = runtime.apply_failsafe("mash_pump")
    assert state.value is False


def test_apply_failsafe_on_non_risk_device_raises(tmp_path):
    config = make_config(tmp_path, YAML_BASIC)
    backend = SimulatedGPIOBackend()
    runtime = DeviceRuntime(config, backend)

    with pytest.raises(DeviceRuntimeError):
        runtime.apply_failsafe("mash_tun_temp")


def test_get_state_unknown_device_raises_key_error(tmp_path):
    config = make_config(tmp_path, YAML_BASIC)
    backend = SimulatedGPIOBackend()
    runtime = DeviceRuntime(config, backend)

    with pytest.raises(KeyError):
        runtime.get_state("does_not_exist")
