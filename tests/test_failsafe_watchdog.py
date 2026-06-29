import textwrap

import pytest

from config import BridgeConfig
from device_runtime import DeviceRuntime
from gpio.simulated_backend import SimulatedGPIOBackend
from failsafe_watchdog import FailsafeTimeoutWatchdog, devices_with_timeout


YAML_CONTENT = """
mqtt:
  enabled: true
backend: simulated
panel:
  enabled: false

devices:
  - id: mash_heater
    name: "Resistencia Mostura"
    role: actuator
    subtype: pwm
    command_topic: "actuators/mash_heater/set"
    hardware:
      pin: 18
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
    failsafe_timeout_seconds: 10

  - id: aux_valve
    name: "Valvula Auxiliar"
    role: actuator
    subtype: digital
    command_topic: "actuators/aux_valve/set"
    hardware:
      pin: 21
    failsafe_value: false
    is_risk: false
"""


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / "devices.yml"
    path.write_text(textwrap.dedent(YAML_CONTENT), encoding="utf-8")
    config = BridgeConfig.load(path)
    backend = SimulatedGPIOBackend()
    runtime = DeviceRuntime(config, backend)
    watchdog = FailsafeTimeoutWatchdog(runtime, devices_with_timeout(runtime))
    return runtime, watchdog


def test_devices_with_timeout_excludes_non_risk_devices(setup):
    runtime, _ = setup
    devices = devices_with_timeout(runtime)
    ids = {d.id for d in devices}
    assert ids == {"mash_heater", "mash_pump"}


def test_check_without_disconnect_does_nothing(setup):
    runtime, watchdog = setup
    runtime.set_actuator("mash_heater", 90.0)
    applied = watchdog.check(now=1000.0)
    assert applied == []
    assert runtime.get_state("mash_heater").value == 90.0


def test_check_before_timeout_does_nothing(setup):
    runtime, watchdog = setup
    runtime.set_actuator("mash_pump", True)
    watchdog.on_disconnect(now=1000.0)

    applied = watchdog.check(now=1005.0)  # só 5s, timeout é 10s
    assert applied == []
    assert runtime.get_state("mash_pump").value is True


def test_check_after_timeout_applies_failsafe(setup):
    runtime, watchdog = setup
    runtime.set_actuator("mash_pump", True)
    watchdog.on_disconnect(now=1000.0)

    applied = watchdog.check(now=1011.0)  # passou de 10s
    assert applied == ["mash_pump"]
    assert runtime.get_state("mash_pump").value is False


def test_check_applies_each_device_at_its_own_timeout(setup):
    runtime, watchdog = setup
    runtime.set_actuator("mash_heater", 90.0)
    runtime.set_actuator("mash_pump", True)
    watchdog.on_disconnect(now=1000.0)

    applied_at_15 = watchdog.check(now=1015.0)  # passou de mash_pump (10s), não de mash_heater (30s)
    assert applied_at_15 == ["mash_pump"]

    applied_at_31 = watchdog.check(now=1031.0)  # agora passou de mash_heater também
    assert applied_at_31 == ["mash_heater"]

    assert runtime.get_state("mash_heater").value == 0.0
    assert runtime.get_state("mash_pump").value is False


def test_check_does_not_reapply_failsafe_repeatedly(setup):
    runtime, watchdog = setup
    watchdog.on_disconnect(now=1000.0)

    watchdog.check(now=1011.0)
    runtime.set_actuator("mash_pump", True)  # alguém liga de novo manualmente

    applied_again = watchdog.check(now=1020.0)
    assert applied_again == []  # watchdog não insiste, já aplicou uma vez neste ciclo de desconexão
    assert runtime.get_state("mash_pump").value is True  # valor manual não é sobrescrito de novo


def test_on_connect_resets_state_for_next_disconnect_cycle(setup):
    runtime, watchdog = setup
    watchdog.on_disconnect(now=1000.0)
    watchdog.check(now=1011.0)  # aplica failsafe em mash_pump

    watchdog.on_connect()  # reconectou

    watchdog.on_disconnect(now=2000.0)  # caiu de novo
    runtime.set_actuator("mash_pump", True)
    applied = watchdog.check(now=2011.0)
    assert applied == ["mash_pump"]  # aplica de novo neste novo ciclo
