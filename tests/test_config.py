import textwrap

import pytest

from config import BridgeConfig, ConfigError


def write_yaml(tmp_path, content: str):
    path = tmp_path / "devices.yml"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


VALID_YAML = """
mqtt:
  enabled: true
  host: localhost
  port: 1883
  topic_prefix: brewery
  reconnect_interval_seconds: 5

backend: simulated

panel:
  enabled: true
  host: 0.0.0.0
  port: 8088

devices:
  - id: mash_tun_temp
    name: "Temperatura Mostura"
    role: sensor
    subtype: temperature
    state_topic: "sensors/mash_tun_temp/state"
    hardware:
      pin: 4
    simulated:
      initial_value: 25.0

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
"""


def test_load_valid_yaml_succeeds(tmp_path):
    path = write_yaml(tmp_path, VALID_YAML)
    config = BridgeConfig.load(path)

    assert config.backend == "simulated"
    assert config.mqtt.topic_prefix == "brewery"
    assert len(config.devices) == 2


def test_load_missing_file_raises_config_error(tmp_path):
    with pytest.raises(ConfigError):
        BridgeConfig.load(tmp_path / "does_not_exist.yml")


def test_resolve_topic_applies_prefix(tmp_path):
    path = write_yaml(tmp_path, VALID_YAML)
    config = BridgeConfig.load(path)
    assert config.resolve_topic("sensors/mash_tun_temp/state") == "brewery/sensors/mash_tun_temp/state"


def test_get_device_returns_correct_device(tmp_path):
    path = write_yaml(tmp_path, VALID_YAML)
    config = BridgeConfig.load(path)
    device = config.get_device("mash_heater")
    assert device.name == "Resistencia Mostura"


def test_get_device_unknown_id_raises_key_error(tmp_path):
    path = write_yaml(tmp_path, VALID_YAML)
    config = BridgeConfig.load(path)
    with pytest.raises(KeyError):
        config.get_device("does_not_exist")


def test_invalid_backend_raises_config_error(tmp_path):
    bad_yaml = VALID_YAML.replace("backend: simulated", "backend: quantum")
    path = write_yaml(tmp_path, bad_yaml)
    with pytest.raises(ConfigError, match="backend inválido"):
        BridgeConfig.load(path)


def test_no_devices_raises_config_error(tmp_path):
    bad_yaml = """
    mqtt:
      enabled: false
    backend: simulated
    panel:
      enabled: false
    devices: []
    """
    path = write_yaml(tmp_path, bad_yaml)
    with pytest.raises(ConfigError, match="ao menos um device"):
        BridgeConfig.load(path)


def test_duplicate_device_id_raises_config_error(tmp_path):
    bad_yaml = """
    mqtt:
      enabled: false
    backend: simulated
    panel:
      enabled: false
    devices:
      - id: sensor_a
        name: "A"
        role: sensor
        state_topic: "sensors/a/state"
        hardware:
          pin: 4
      - id: sensor_a
        name: "A duplicado"
        role: sensor
        state_topic: "sensors/a2/state"
        hardware:
          pin: 5
    """
    path = write_yaml(tmp_path, bad_yaml)
    with pytest.raises(ConfigError, match="duplicado"):
        BridgeConfig.load(path)


def test_duplicate_pin_raises_config_error(tmp_path):
    bad_yaml = """
    mqtt:
      enabled: false
    backend: simulated
    panel:
      enabled: false
    devices:
      - id: sensor_a
        name: "A"
        role: sensor
        state_topic: "sensors/a/state"
        hardware:
          pin: 4
      - id: sensor_b
        name: "B"
        role: sensor
        state_topic: "sensors/b/state"
        hardware:
          pin: 4
    """
    path = write_yaml(tmp_path, bad_yaml)
    with pytest.raises(ConfigError, match="usado em mais de um device"):
        BridgeConfig.load(path)


def test_sensor_without_state_topic_raises_config_error(tmp_path):
    bad_yaml = """
    mqtt:
      enabled: false
    backend: simulated
    panel:
      enabled: false
    devices:
      - id: sensor_a
        name: "A"
        role: sensor
        hardware:
          pin: 4
    """
    path = write_yaml(tmp_path, bad_yaml)
    with pytest.raises(ConfigError, match="state_topic"):
        BridgeConfig.load(path)


def test_sensor_with_command_topic_raises_config_error(tmp_path):
    bad_yaml = """
    mqtt:
      enabled: false
    backend: simulated
    panel:
      enabled: false
    devices:
      - id: sensor_a
        name: "A"
        role: sensor
        state_topic: "sensors/a/state"
        command_topic: "sensors/a/set"
        hardware:
          pin: 4
    """
    path = write_yaml(tmp_path, bad_yaml)
    with pytest.raises(ConfigError, match="não deve declarar command_topic"):
        BridgeConfig.load(path)


def test_actuator_without_command_topic_raises_config_error(tmp_path):
    bad_yaml = """
    mqtt:
      enabled: false
    backend: simulated
    panel:
      enabled: false
    devices:
      - id: act_a
        name: "A"
        role: actuator
        hardware:
          pin: 18
    """
    path = write_yaml(tmp_path, bad_yaml)
    with pytest.raises(ConfigError, match="command_topic"):
        BridgeConfig.load(path)


def test_is_risk_without_failsafe_value_raises_config_error(tmp_path):
    bad_yaml = """
    mqtt:
      enabled: false
    backend: simulated
    panel:
      enabled: false
    devices:
      - id: act_a
        name: "A"
        role: actuator
        command_topic: "actuators/a/set"
        hardware:
          pin: 18
        is_risk: true
    """
    path = write_yaml(tmp_path, bad_yaml)
    with pytest.raises(ConfigError, match="failsafe_value"):
        BridgeConfig.load(path)


def test_failsafe_timeout_without_is_risk_raises_config_error(tmp_path):
    bad_yaml = """
    mqtt:
      enabled: false
    backend: simulated
    panel:
      enabled: false
    devices:
      - id: act_a
        name: "A"
        role: actuator
        command_topic: "actuators/a/set"
        hardware:
          pin: 18
        failsafe_timeout_seconds: 30
    """
    path = write_yaml(tmp_path, bad_yaml)
    with pytest.raises(ConfigError, match="failsafe_timeout_seconds só faz sentido"):
        BridgeConfig.load(path)


def test_failsafe_timeout_must_be_positive_int(tmp_path):
    bad_yaml = """
    mqtt:
      enabled: false
    backend: simulated
    panel:
      enabled: false
    devices:
      - id: act_a
        name: "A"
        role: actuator
        command_topic: "actuators/a/set"
        hardware:
          pin: 18
        is_risk: true
        failsafe_value: 0
        failsafe_timeout_seconds: -5
    """
    path = write_yaml(tmp_path, bad_yaml)
    with pytest.raises(ConfigError, match="deve ser inteiro > 0"):
        BridgeConfig.load(path)


def test_missing_pin_raises_config_error(tmp_path):
    bad_yaml = """
    mqtt:
      enabled: false
    backend: simulated
    panel:
      enabled: false
    devices:
      - id: act_a
        name: "A"
        role: actuator
        command_topic: "actuators/a/set"
        hardware: {}
    """
    path = write_yaml(tmp_path, bad_yaml)
    with pytest.raises(ConfigError, match="hardware.pin"):
        BridgeConfig.load(path)


def test_invalid_role_raises_config_error(tmp_path):
    bad_yaml = """
    mqtt:
      enabled: false
    backend: simulated
    panel:
      enabled: false
    devices:
      - id: dev_a
        name: "A"
        role: gizmo
        hardware:
          pin: 4
    """
    path = write_yaml(tmp_path, bad_yaml)
    with pytest.raises(ConfigError, match="role inválido"):
        BridgeConfig.load(path)


def test_mqtt_disabled_skips_host_validation(tmp_path):
    """
    Com mqtt.enabled=false, host/port/topic_prefix não são obrigatórios —
    o bridge deve poder rodar em modo painel-only sem nenhuma config de
    MQTT preenchida.
    """
    yaml_content = """
    mqtt:
      enabled: false
    backend: simulated
    panel:
      enabled: true
      port: 8088
    devices:
      - id: sensor_a
        name: "A"
        role: sensor
        state_topic: "sensors/a/state"
        hardware:
          pin: 4
    """
    path = write_yaml(tmp_path, yaml_content)
    config = BridgeConfig.load(path)
    assert config.mqtt.enabled is False


def test_example_yaml_in_repo_is_valid():
    """
    O devices.yml.example versionado no repo precisa, ele mesmo, passar
    pela validação — senão a documentação do projeto está mentindo sobre
    o próprio schema que ela define.
    """
    config = BridgeConfig.load("devices.yml.example")
    assert config.backend == "simulated"
    assert len(config.devices) == 3
