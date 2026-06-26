"""
DeviceRuntime — conecta a configuração validada (BridgeConfig) a um
GPIOBackend concreto (simulado ou real).

Esta camada existe para não duplicar a lógica de "qual modo de pino usar
para qual combinação de role/subtype" tanto no painel web (Fase 3)
quanto no bridge MQTT (Fase 4) — os dois consomem DeviceRuntime, nunca
o GPIOBackend diretamente.

Não conhece MQTT. Não conhece HTTP. Só sabe traduzir DeviceConfig <->
GPIOBackend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from config import BridgeConfig, DeviceConfig
from gpio.base import GPIOBackend

# Mapeia (role, subtype) -> mode aceito por GPIOBackend.setup().
# subtype=None cai no default de cada role (digital).
_MODE_MAP = {
    ("sensor", "temperature"): "input_analog",
    ("sensor", "analog"): "input_analog",
    ("sensor", "digital"): "input",
    ("sensor", None): "input",
    ("actuator", "pwm"): "pwm",
    ("actuator", "digital"): "output",
    ("actuator", None): "output",
}


class DeviceRuntimeError(RuntimeError):
    """Erro de uso do DeviceRuntime — ex.: operação incompatível com o role do device."""


@dataclass
class DeviceState:
    id: str
    name: str
    role: str
    subtype: str | None
    unit: str | None
    value: Any
    is_risk: bool
    failsafe_value: Any
    range: Dict[str, Any]


def resolve_mode(role: str, subtype: str | None) -> str:
    mode = _MODE_MAP.get((role, subtype))
    if mode is None:
        # subtype desconhecido para o role: cai no default daquele role
        # em vez de falhar, já que novos subtypes (ex.: "humidity") podem
        # ser adicionados ao devices.yml sem exigir mudança de código aqui.
        mode = _MODE_MAP[(role, None)]
    return mode


class DeviceRuntime:
    """
    Liga cada DeviceConfig a um pino do GPIOBackend, e expõe operações
    de alto nível (list, read, set_actuator, inject_sensor) que tanto o
    painel quanto o bridge MQTT usam.
    """

    def __init__(self, config: BridgeConfig, backend: GPIOBackend) -> None:
        self._config = config
        self._backend = backend
        self._setup_all()

    def _setup_all(self) -> None:
        for device in self._config.devices:
            mode = resolve_mode(device.role, device.subtype)
            kwargs: Dict[str, Any] = {}
            kwargs.update(device.simulated)
            kwargs.update(device.limits)
            if "pwm_frequency" in device.hardware:
                kwargs["pwm_frequency"] = device.hardware["pwm_frequency"]
            self._backend.setup(pin=device.hardware["pin"], mode=mode, **kwargs)

    def list_devices(self) -> List[DeviceState]:
        return [self._state_of(device) for device in self._config.devices]

    def get_state(self, device_id: str) -> DeviceState:
        device = self._config.get_device(device_id)
        return self._state_of(device)

    def set_actuator(self, device_id: str, value: Any) -> DeviceState:
        """
        Aciona um atuador diretamente (sem passar por MQTT) — usado pelo
        painel manual e, na Fase 4, também pelo bridge ao receber comando
        via command_topic.
        """
        device = self._config.get_device(device_id)
        if device.role != "actuator":
            raise DeviceRuntimeError(
                f"set_actuator chamado em '{device_id}', que não é actuator (role='{device.role}')."
            )
        self._backend.write(device.hardware["pin"], value)
        return self._state_of(device)

    def inject_sensor(self, device_id: str, value: Any) -> DeviceState:
        """
        Injeta um valor fake em um sensor simulado (painel ajustando um
        slider). Só faz sentido com SimulatedGPIOBackend — se o backend
        real não tiver inject(), o erro sobe naturalmente como
        AttributeError, e quem chama (panel/api.py) decide como tratar
        isso para o usuário.
        """
        device = self._config.get_device(device_id)
        if device.role != "sensor":
            raise DeviceRuntimeError(
                f"inject_sensor chamado em '{device_id}', que não é sensor (role='{device.role}')."
            )
        self._backend.inject(device.hardware["pin"], value)
        return self._state_of(device)

    def apply_failsafe(self, device_id: str) -> DeviceState:
        """
        Aplica failsafe_value localmente a um atuador de risco — usado
        pela lógica de failsafe_timeout_seconds na Fase 4. Aqui na Fase 3
        só existe para já deixar a operação testável isoladamente.
        """
        device = self._config.get_device(device_id)
        if not device.is_risk:
            raise DeviceRuntimeError(
                f"apply_failsafe chamado em '{device_id}', que não é is_risk=true."
            )
        return self.set_actuator(device_id, device.failsafe_value)

    def _state_of(self, device: DeviceConfig) -> DeviceState:
        value = self._backend.read(device.hardware["pin"])
        source = device.simulated if device.role == "sensor" else device.limits
        device_range = {
            "min": source.get("min", 0),
            "max": source.get("max", 100),
        }
        return DeviceState(
            id=device.id,
            name=device.name,
            role=device.role,
            subtype=device.subtype,
            unit=device.unit,
            value=value,
            is_risk=device.is_risk,
            failsafe_value=device.failsafe_value,
            range=device_range,
        )
