"""
Backend real de GPIO, usando gpiozero (preferível a RPi.GPIO puro —
API mais simples para digital/PWM, conforme seção 7 da spec).

Testável fora do Pi via gpiozero.pins.mock (MockFactory + MockPWMPin),
mas isso só valida a "fiação" (qual classe gpiozero é instanciada para
qual mode) — não substitui um teste real em hardware físico. Marcar
qualquer teste contra este módulo como smoke test de wiring, nunca como
prova de que o GPIO real funciona.

`input_analog` (ex.: leitura de termistor/ADC) não tem suporte nativo
genérico no gpiozero sem um chip ADC dedicado (MCP3008 etc.) ou um
sensor 1-Wire (ds18b20). Resolvido via um pequeno registro de drivers
(`hardware.driver` no devices.yml) — sem driver reconhecido, levanta
NotImplementedError explícito em vez de falhar tentando ler um pino
digital comum como se fosse analógico.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from gpiozero import DigitalInputDevice, DigitalOutputDevice, PWMOutputDevice

from gpio.base import GPIOBackend

logger = logging.getLogger("tesseract_bridge.gpio.real")

# Registro de drivers para sensores que não são GPIO digital/PWM simples.
# Cada driver recebe (pin, **config) e retorna um objeto com .value (ou
# uma função de leitura) — ver _Ds18b20Reader como exemplo de contrato.
_ANALOG_DRIVERS: Dict[str, Callable[..., Any]] = {}


def register_analog_driver(name: str, factory: Callable[..., Any]) -> None:
    """
    Permite registrar um driver de sensor analógico/1-Wire sem precisar
    editar este arquivo (ex.: um driver de ds18b20 real, implementado e
    testado só quando houver Pi com o sensor conectado).
    """
    _ANALOG_DRIVERS[name] = factory


class RealGPIOBackend(GPIOBackend):
    """
    Implementação de GPIOBackend sobre hardware real (ou MockFactory do
    gpiozero, para wiring test sem Pi).
    """

    def __init__(self) -> None:
        self._devices: Dict[int, Any] = {}
        self._modes: Dict[int, str] = {}

    def setup(self, pin: int, mode: str, **kwargs: Any) -> None:
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

        self._devices[pin] = device
        self._modes[pin] = mode
        logger.info("setup: pino=%s mode=%s", pin, mode)

    def read(self, pin: int) -> Any:
        device = self._require_device(pin)
        mode = self._modes[pin]
        value = device.value
        if mode == "pwm":
            # gpiozero usa 0.0-1.0 internamente; o resto do bridge
            # trabalha em 0-100 (ver devices.yml.example, limits.max=100).
            return value * 100.0
        logger.debug("read: pino=%s mode=%s value=%s", pin, mode, value)
        return value

    def write(self, pin: int, value: Any) -> None:
        device = self._require_device(pin)
        mode = self._modes[pin]
        if mode not in ("output", "pwm"):
            raise ValueError(
                f"write() chamado em pino {pin} com mode='{mode}', "
                f"mas write só é permitido em modos 'output'/'pwm'."
            )
        if mode == "pwm":
            device.value = max(0.0, min(1.0, float(value) / 100.0))
        else:
            device.value = bool(value)
        logger.info("write: pino=%s mode=%s value=%s", pin, mode, value)

    def teardown(self, pin: int) -> None:
        device = self._devices.pop(pin, None)
        self._modes.pop(pin, None)
        if device is not None:
            device.close()
            logger.info("teardown: pino=%s", pin)

    def _require_device(self, pin: int) -> Any:
        if pin not in self._devices:
            raise KeyError(f"Pino {pin} não foi configurado via setup() antes do uso.")
        return self._devices[pin]
