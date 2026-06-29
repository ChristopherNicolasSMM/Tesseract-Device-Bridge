import json
import textwrap
from unittest.mock import MagicMock, patch

import pytest

from bridge import Bridge
from config import BridgeConfig
from device_runtime import DeviceRuntime
from gpio.simulated_backend import SimulatedGPIOBackend


YAML_MQTT_DISABLED = """
mqtt:
  enabled: false
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


YAML_MQTT_ENABLED = YAML_MQTT_DISABLED.replace("enabled: false\nbackend", "enabled: true\nbackend")


def build_bridge(tmp_path, yaml_content):
    path = tmp_path / "devices.yml"
    path.write_text(textwrap.dedent(yaml_content), encoding="utf-8")
    config = BridgeConfig.load(path)
    backend = SimulatedGPIOBackend()
    runtime = DeviceRuntime(config, backend)
    return Bridge(config, runtime), runtime, config


def test_mqtt_disabled_does_not_create_client(tmp_path):
    bridge, runtime, config = build_bridge(tmp_path, YAML_MQTT_DISABLED)
    assert bridge._mqtt is None


def test_handle_command_message_with_json_payload(tmp_path):
    bridge, runtime, config = build_bridge(tmp_path, YAML_MQTT_DISABLED)
    bridge._handle_command_message("mash_heater", json.dumps({"value": 55.0}))
    assert runtime.get_state("mash_heater").value == 55.0


def test_handle_command_message_with_raw_payload(tmp_path):
    bridge, runtime, config = build_bridge(tmp_path, YAML_MQTT_DISABLED)
    bridge._handle_command_message("mash_heater", "33.0")
    assert runtime.get_state("mash_heater").value == 33.0


def test_handle_command_message_unknown_device_does_not_raise(tmp_path):
    bridge, runtime, config = build_bridge(tmp_path, YAML_MQTT_DISABLED)
    bridge._handle_command_message("does_not_exist", json.dumps({"value": 1}))  # não deve lançar


def test_publish_sensor_states_noop_when_mqtt_disabled(tmp_path):
    bridge, runtime, config = build_bridge(tmp_path, YAML_MQTT_DISABLED)
    bridge.publish_sensor_states()  # não deve lançar nem fazer nada perceptível


def test_check_watchdog_delegates_to_watchdog_instance(tmp_path):
    bridge, runtime, config = build_bridge(tmp_path, YAML_MQTT_DISABLED)
    bridge.watchdog.on_disconnect(now=1000.0)
    applied = bridge.check_watchdog(now=1031.0)
    assert applied == ["mash_heater"]
    assert runtime.get_state("mash_heater").value == 0.0


def test_status_handler_property_applies_failsafe(tmp_path):
    bridge, runtime, config = build_bridge(tmp_path, YAML_MQTT_DISABLED)
    runtime.set_actuator("mash_heater", 90.0)

    payload = json.dumps({
        "status": "offline",
        "failsafe_actuators": [
            {"command_topic": "actuators/mash_heater/set", "failsafe_value": "0"}
        ],
    })
    # Nota: aqui o command_topic completo (com prefixo "brewery" default)
    # precisa bater com o lookup; usando topic_prefix default "brewery".
    bridge.status_handler.handle_message(payload.replace(
        "actuators/mash_heater/set", "brewery/actuators/mash_heater/set"
    ))
    assert runtime.get_state("mash_heater").value == 0.0


@patch("mqtt_client.mqtt.Client")
def test_mqtt_enabled_creates_client_and_subscribes_on_connect(mock_client_cls, tmp_path):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    bridge, runtime, config = build_bridge(tmp_path, YAML_MQTT_ENABLED)
    assert bridge._mqtt is not None

    bridge.start()
    mock_client.connect.assert_called_once()
    mock_client.loop_start.assert_called_once()

    # Simula o callback on_connect do paho sendo disparado pelo broker real
    on_connect = mock_client.on_connect
    on_connect(mock_client, None, None, 0)

    subscribed_topics = [call.args[0] for call in mock_client.subscribe.call_args_list]
    assert "brewery/system/tesseract/status" in subscribed_topics
    assert "brewery/actuators/mash_heater/set" in subscribed_topics


@patch("mqtt_client.mqtt.Client")
def test_mqtt_message_routing_to_status_handler(mock_client_cls, tmp_path):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    bridge, runtime, config = build_bridge(tmp_path, YAML_MQTT_ENABLED)
    runtime.set_actuator("mash_heater", 90.0)

    on_message = mock_client.on_message
    fake_msg = MagicMock()
    fake_msg.topic = "brewery/system/tesseract/status"
    fake_msg.payload = json.dumps({
        "status": "offline",
        "failsafe_actuators": [
            {"command_topic": "brewery/actuators/mash_heater/set", "failsafe_value": "0"}
        ],
    }).encode("utf-8")

    on_message(mock_client, None, fake_msg)
    assert runtime.get_state("mash_heater").value == 0.0


@patch("mqtt_client.mqtt.Client")
def test_mqtt_message_routing_to_command_handler(mock_client_cls, tmp_path):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    bridge, runtime, config = build_bridge(tmp_path, YAML_MQTT_ENABLED)

    on_message = mock_client.on_message
    fake_msg = MagicMock()
    fake_msg.topic = "brewery/actuators/mash_heater/set"
    fake_msg.payload = json.dumps({"value": 42.0}).encode("utf-8")

    on_message(mock_client, None, fake_msg)
    assert runtime.get_state("mash_heater").value == 42.0


@patch("mqtt_client.mqtt.Client")
def test_disconnect_callback_wires_to_watchdog(mock_client_cls, tmp_path):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    bridge, runtime, config = build_bridge(tmp_path, YAML_MQTT_ENABLED)

    on_disconnect = mock_client.on_disconnect
    on_disconnect(mock_client, None, 0)

    # watchdog já deve ter registrado a desconexão; um check bem no futuro aplica failsafe
    applied = bridge.check_watchdog(now=time_now_plus(31))
    assert applied == ["mash_heater"]


def time_now_plus(seconds):
    import time
    return time.time() + seconds
