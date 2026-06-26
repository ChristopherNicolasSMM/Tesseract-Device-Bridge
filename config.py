"""
Carregamento e validação de `devices.yml`.

Usa dataclasses + validação manual (sem pydantic, conforme decisão da
spec — seção 7, "Config YAML: pyyaml + validação manual ou pydantic").

Nenhuma parte do bridge (mqtt_client.py, bridge.py, panel/) deve ler o
YAML diretamente — sempre passam por `BridgeConfig.load()` e trabalham
com os objetos já validados daqui.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

_VALID_BACKENDS = {"real", "simulated"}
_VALID_ROLES = {"sensor", "actuator"}


class ConfigError(ValueError):
    """Erro de validação de devices.yml — sempre com mensagem explicando o que está errado e onde."""


@dataclass
class MqttConfig:
    enabled: bool = True
    host: str = "localhost"
    port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None
    client_id: str = "tesseract_bridge"
    topic_prefix: str = "brewery"
    reconnect_interval_seconds: int = 5

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "MqttConfig":
        return cls(
            enabled=raw.get("enabled", True),
            host=raw.get("host", "localhost"),
            port=raw.get("port", 1883),
            username=raw.get("username"),
            password=raw.get("password"),
            client_id=raw.get("client_id", "tesseract_bridge"),
            topic_prefix=raw.get("topic_prefix", "brewery"),
            reconnect_interval_seconds=raw.get("reconnect_interval_seconds", 5),
        )

    def validate(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ConfigError("mqtt.enabled deve ser bool (true/false).")
        if self.enabled:
            if not self.host or not isinstance(self.host, str):
                raise ConfigError("mqtt.host é obrigatório (string) quando mqtt.enabled=true.")
            if not isinstance(self.port, int) or self.port <= 0:
                raise ConfigError("mqtt.port deve ser um inteiro positivo.")
            if not self.topic_prefix or not isinstance(self.topic_prefix, str):
                raise ConfigError("mqtt.topic_prefix é obrigatório quando mqtt.enabled=true.")
        if self.reconnect_interval_seconds <= 0:
            raise ConfigError("mqtt.reconnect_interval_seconds deve ser > 0.")


@dataclass
class PanelConfig:
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8088

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "PanelConfig":
        return cls(
            enabled=raw.get("enabled", True),
            host=raw.get("host", "0.0.0.0"),
            port=raw.get("port", 8088),
        )

    def validate(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ConfigError("panel.enabled deve ser bool (true/false).")
        if self.enabled and (not isinstance(self.port, int) or self.port <= 0):
            raise ConfigError("panel.port deve ser um inteiro positivo quando panel.enabled=true.")


@dataclass
class DeviceConfig:
    id: str
    name: str
    role: str
    subtype: Optional[str] = None
    unit: Optional[str] = None
    state_topic: Optional[str] = None
    command_topic: Optional[str] = None
    hardware: Dict[str, Any] = field(default_factory=dict)
    simulated: Dict[str, Any] = field(default_factory=dict)
    failsafe_value: Any = None
    is_risk: bool = False
    failsafe_timeout_seconds: Optional[int] = None
    limits: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "DeviceConfig":
        missing = [k for k in ("id", "name", "role") if k not in raw]
        if missing:
            raise ConfigError(f"Device sem campo(s) obrigatório(s) {missing}: {raw}")
        return cls(
            id=raw["id"],
            name=raw["name"],
            role=raw["role"],
            subtype=raw.get("subtype"),
            unit=raw.get("unit"),
            state_topic=raw.get("state_topic"),
            command_topic=raw.get("command_topic"),
            hardware=raw.get("hardware", {}) or {},
            simulated=raw.get("simulated", {}) or {},
            failsafe_value=raw.get("failsafe_value"),
            is_risk=raw.get("is_risk", False),
            failsafe_timeout_seconds=raw.get("failsafe_timeout_seconds"),
            limits=raw.get("limits", {}) or {},
        )

    def validate(self) -> None:
        prefix = f"device '{self.id}'"

        if self.role not in _VALID_ROLES:
            raise ConfigError(f"{prefix}: role inválido '{self.role}', esperado um de {sorted(_VALID_ROLES)}.")

        if "pin" not in self.hardware:
            raise ConfigError(f"{prefix}: hardware.pin é obrigatório.")
        if not isinstance(self.hardware["pin"], int):
            raise ConfigError(f"{prefix}: hardware.pin deve ser inteiro.")

        if self.role == "sensor":
            if not self.state_topic:
                raise ConfigError(f"{prefix}: sensor requer state_topic.")
            if self.command_topic:
                raise ConfigError(f"{prefix}: sensor não deve declarar command_topic.")

        if self.role == "actuator":
            if not self.command_topic:
                raise ConfigError(f"{prefix}: actuator requer command_topic.")

        if self.is_risk and self.failsafe_value is None:
            raise ConfigError(
                f"{prefix}: is_risk=true requer failsafe_value explícito "
                f"(mesmo que seja um valor 'neutro' como 0 ou false)."
            )

        if self.failsafe_timeout_seconds is not None:
            if not self.is_risk:
                raise ConfigError(
                    f"{prefix}: failsafe_timeout_seconds só faz sentido com is_risk=true."
                )
            if not isinstance(self.failsafe_timeout_seconds, int) or self.failsafe_timeout_seconds <= 0:
                raise ConfigError(f"{prefix}: failsafe_timeout_seconds deve ser inteiro > 0.")


@dataclass
class BridgeConfig:
    mqtt: MqttConfig
    panel: PanelConfig
    backend: str
    devices: List[DeviceConfig]

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "BridgeConfig":
        backend = raw.get("backend", "simulated")
        devices_raw = raw.get("devices", [])
        return cls(
            mqtt=MqttConfig.from_dict(raw.get("mqtt", {}) or {}),
            panel=PanelConfig.from_dict(raw.get("panel", {}) or {}),
            backend=backend,
            devices=[DeviceConfig.from_dict(d) for d in devices_raw],
        )

    @classmethod
    def load(cls, path: str | Path) -> "BridgeConfig":
        """
        Carrega e valida `devices.yml` a partir de um caminho de arquivo.
        Levanta ConfigError com mensagem explicando exatamente o que está
        errado — nunca falha silenciosamente nem com traceback genérico
        de KeyError/TypeError.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise ConfigError(f"Arquivo de configuração não encontrado: {file_path}")

        with file_path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        config = cls.from_dict(raw)
        config.validate()
        return config

    def validate(self) -> None:
        if self.backend not in _VALID_BACKENDS:
            raise ConfigError(
                f"backend inválido '{self.backend}', esperado um de {sorted(_VALID_BACKENDS)}."
            )

        self.mqtt.validate()
        self.panel.validate()

        if not self.devices:
            raise ConfigError("devices.yml deve declarar ao menos um device em 'devices'.")

        seen_ids: Dict[str, int] = {}
        seen_pins: Dict[int, str] = {}

        for device in self.devices:
            device.validate()

            if device.id in seen_ids:
                raise ConfigError(f"id de device duplicado: '{device.id}'.")
            seen_ids[device.id] = 1

            pin = device.hardware["pin"]
            if pin in seen_pins:
                raise ConfigError(
                    f"hardware.pin {pin} usado em mais de um device "
                    f"('{seen_pins[pin]}' e '{device.id}')."
                )
            seen_pins[pin] = device.id

    def resolve_topic(self, topic: str) -> str:
        """
        Aplica o `topic_prefix` a um tópico relativo declarado em um
        device (ex.: "sensors/mash_tun_temp/state" -> "brewery/sensors/mash_tun_temp/state").
        """
        return f"{self.mqtt.topic_prefix}/{topic}"

    def get_device(self, device_id: str) -> DeviceConfig:
        for device in self.devices:
            if device.id == device_id:
                return device
        raise KeyError(f"Device '{device_id}' não existe na configuração carregada.")
