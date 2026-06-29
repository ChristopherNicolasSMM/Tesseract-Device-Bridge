import json
import textwrap

import pytest

from config import BridgeConfig
from device_runtime import DeviceRuntime
from gpio.simulated_backend import SimulatedGPIOBackend
from status_handler import StatusTopicHandler, build_command_topic_lookup


YAML_CONTENT = """
mqtt:
  enabled: true
  topic_prefix: brewery
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
    failsafe_timeout_seconds: 30

  - id: mash_tun_temp
    name: "Temperatura Mostura"
    role: sensor
    subtype: temperature
    state_topic: "sensors/mash_tun_temp/state"
    hardware:
      pin: 4
    simulated:
      initial_value: 25.0
"""


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / "devices.yml"
    path.write_text(textwrap.dedent(YAML_CONTENT), encoding="utf-8")
    config = BridgeConfig.load(path)
    backend = SimulatedGPIOBackend()
    runtime = DeviceRuntime(config, backend)
    lookup = build_command_topic_lookup(runtime, config.resolve_topic)
    handler = StatusTopicHandler(runtime, lookup)
    return runtime, handler, config


def test_lookup_only_includes_actuators_with_command_topic(setup):
    runtime, handler, config = setup
    lookup = build_command_topic_lookup(runtime, config.resolve_topic)
    assert lookup == {
        "brewery/actuators/mash_heater/set": "mash_heater",
        "brewery/actuators/mash_pump/set": "mash_pump",
    }


def test_offline_status_applies_failsafe_for_matched_actuator(setup):
    runtime, handler, config = setup
    runtime.set_actuator("mash_heater", 80.0)

    payload = json.dumps({
        "status": "offline",
        "failsafe_actuators": [
            {
                "external_id": "some-uuid-not-used-for-matching",
                "name": "Resistência Mostura",
                "command_topic": "brewery/actuators/mash_heater/set",
                "failsafe_value": "0",
            }
        ],
    })
    handler.handle_message(payload)

    assert runtime.get_state("mash_heater").value == 0.0
    assert handler.last_status == "offline"


def test_offline_status_coerces_digital_failsafe_value(setup):
    runtime, handler, config = setup
    runtime.set_actuator("mash_pump", True)

    payload = json.dumps({
        "status": "offline",
        "failsafe_actuators": [
            {
                "external_id": "uuid-2",
                "name": "Bomba",
                "command_topic": "brewery/actuators/mash_pump/set",
                "failsafe_value": "false",
            }
        ],
    })
    handler.handle_message(payload)

    assert runtime.get_state("mash_pump").value is False


def test_offline_status_ignores_unmatched_command_topic(setup):
    """
    Atuador que o Tesseract conhece mas não existe (ou tem outro
    command_topic) no devices.yml local — ignorado silenciosamente,
    não deve levantar exceção nem afetar outros devices.
    """
    runtime, handler, config = setup
    payload = json.dumps({
        "status": "offline",
        "failsafe_actuators": [
            {
                "external_id": "uuid-x",
                "name": "Atuador desconhecido",
                "command_topic": "brewery/actuators/nao_existe/set",
                "failsafe_value": "0",
            }
        ],
    })
    handler.handle_message(payload)  # não deve lançar
    assert handler.last_status == "offline"


def test_online_status_does_not_change_actuator_value(setup):
    """
    Decisão registrada: ao voltar para online, nenhuma ação automática —
    o atuador permanece no failsafe_value até receber comando normal.
    """
    runtime, handler, config = setup
    runtime.set_actuator("mash_heater", 0.0)  # já em failsafe

    payload = json.dumps({"status": "online"})
    handler.handle_message(payload)

    assert runtime.get_state("mash_heater").value == 0.0
    assert handler.last_status == "online"


def test_invalid_json_payload_is_ignored_without_raising(setup):
    runtime, handler, config = setup
    handler.handle_message("isto não é json")  # não deve lançar
    assert handler.last_status is None


def test_unknown_status_field_is_logged_and_ignored(setup):
    runtime, handler, config = setup
    handler.handle_message(json.dumps({"status": "degraded"}))
    assert handler.last_status == "degraded"


def test_multiple_actuators_in_single_payload(setup):
    runtime, handler, config = setup
    payload = json.dumps({
        "status": "offline",
        "failsafe_actuators": [
            {"command_topic": "brewery/actuators/mash_heater/set", "failsafe_value": "0"},
            {"command_topic": "brewery/actuators/mash_pump/set", "failsafe_value": "false"},
        ],
    })
    handler.handle_message(payload)

    assert runtime.get_state("mash_heater").value == 0.0
    assert runtime.get_state("mash_pump").value is False
