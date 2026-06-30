"""
Backend real de GPIO, usando gpiozero (preferível a RPi.GPIO puro —
API mais simples para digital/PWM, conforme seção 7 da spec).

Testável fora do Pi via gpiozero.pins.mock (MockFactory + MockPWMPin),
mas isso só valida a "fiação" (qual classe gpiozero é instanciada para
qual mode) — não substitui um teste real em hardware físico. Marcar
qualquer teste contra este módulo como smoke test de wiring, nunca como
prova de que o GPIO real funciona.

`input_analog` (ex.: leitura de termistor/ADC/1-Wire) não tem suporte
nativo genérico no gpiozero. Resolvido via um pequeno registro de
drivers (`hardware.driver` no devices.yml) — sem driver reconhecido,
levanta NotImplementedError explícito em vez de falhar tentando ler um
pino digital comum como se fosse analógico.

Suporta múltiplos devices no mesmo `pin` via `address` (caso real: 3
sensores DS18B20 no barramento 1-Wire da interface CraftBeerPi/MAZZA,
todos em GPIO4, distinguidos pelo endereço ROM gravado de fábrica em
cada sensor) — ver gpio/ds18b20_scan.py para descobrir os endereços
conectados.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Union

from gpiozero import DigitalInputDevice, DigitalOutputDevice, PWMOutputDevice

from gpio.base import GPIOBackend
from gpio.ds18b20_driver import Ds18b20Reader

logger = logging.getLogger("tesseract_bridge.gpio.real")

_Key = Union[int, "tuple[int, str]"]


def _make_key(pin: int, address: Optional[str]) -> _Key:
    return pin if address is None else (pin, address)


# Registro de drivers para sensores que não são GPIO digital/PWM simples.
# Cada driver recebe (pin, **config) e retorna um objeto com .value.
_ANALOG_DRIVERS: Dict[str, Callable[..., Any]] = {
    "ds18b20": Ds18b20Reader,
}


def register_analog_driver(name: str, factory: Callable[..., Any]) -> None:
    """
    Permite registrar (ou sobrescrever, ex.: em teste) um driver de
    sensor analógico/1-Wire sem precisar editar este arquivo.
    """
    _ANALOG_DRIVERS[name] = factory


class RealGPIOBackend(GPIOBackend):
    """
    Implementação de GPIOBackend sobre hardware real (ou MockFactory do
    gpiozero, para wiring test sem Pi).
    """

    def __init__(self) -> None:
        self._devices: Dict[_Key, Any] = {}
        self._modes: Dict[_Key, str] = {}

    def setup(self, pin: int, mode: str, **kwargs: Any) -> None:
        address = kwargs.get("address")
        key = _make_key(pin, address)

        if mode == "output":
            device = DigitalOutputDevice(pin)
        elif mode == "pwm":
            frequency = kwargs.get("pwm_frequency", 100)
            device = PWMOutputDevice(pin, frequency=frequency)
        elif mode == "input":
            device = DigitalInputDevice(pin)
        elif mode == "input_analog":
            driver_name = kwargs.get("driver")
            driver = _ANALOG_DRIVERS.get(driver_name)
            if driver is None:
                raise NotImplementedError(
                    f"Nenhum driver analógico registrado para '{driver_name}' "
                    f"(pino {pin}). Drivers disponíveis: {sorted(_ANALOG_DRIVERS)}. "
                    f"Registrar via register_analog_driver() antes de setup()."
                )
            device = driver(pin, **kwargs)
        else:
            raise ValueError(f"Modo inválido '{mode}' para pino {pin}.")

        self._devices[key] = device
        self._modes[key] = mode
        logger.info("setup: pino=%s address=%s mode=%s", pin, address, mode)

    def read(self, pin: int, address: Optional[str] = None) -> Any:
        key = _make_key(pin, address)
        device = self._require_device(key, pin, address)
        mode = self._modes[key]
        value = device.value
        if mode == "pwm":
            # gpiozero usa 0.0-1.0 internamente; o resto do bridge
            # trabalha em 0-100.
            return value * 100.0
        logger.debug("read: pino=%s address=%s mode=%s value=%s", pin, address, mode, value)
        return value

    def write(self, pin: int, value: Any, address: Optional[str] = None) -> None:
        key = _make_key(pin, address)
        device = self._require_device(key, pin, address)
        mode = self._modes[key]
        if mode not in ("output", "pwm"):
            raise ValueError(
                f"write() chamado em pino {pin} com mode='{mode}', "
                f"mas write só é permitido em modos 'output'/'pwm'."
            )
        if mode == "pwm":
            device.value = max(0.0, min(1.0, float(value) / 100.0))
        else:
            device.value = bool(value)
        logger.info("write: pino=%s address=%s mode=%s value=%s", pin, address, mode, value)

    def teardown(self, pin: int, address: Optional[str] = None) -> None:
        key = _make_key(pin, address)
        device = self._devices.pop(key, None)
        self._modes.pop(key, None)
        if device is not None and hasattr(device, "close"):
            device.close()
            logger.info("teardown: pino=%s address=%s", pin, address)

    def _require_device(self, key: _Key, pin: int, address: Optional[str]) -> Any:
        if key not in self._devices:
            suffix = f" (address={address})" if address is not None else ""
            raise KeyError(f"Pino {pin}{suffix} não foi configurado via setup() antes do uso.")
        return self._devices[key]
