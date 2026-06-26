"""
Backend simulado de GPIO.

Mantém o estado de cada pino em memória (sem nenhuma dependência de
hardware), loga toda escrita/leitura, e permite injetar valores "fake"
de sensor via `inject()` — usado tanto em testes automatizados quanto
pelo painel web (quando o usuário ajusta um slider de sensor simulado).

Roda em qualquer máquina (Windows/Mac/Linux/Pi), sem nenhuma lib de
hardware instalada.
"""

import logging
from typing import Any, Dict

from gpio.base import GPIOBackend

logger = logging.getLogger("tesseract_bridge.gpio.simulated")

_VALID_MODES = {"input", "output", "pwm", "input_analog"}
_OUTPUT_MODES = {"output", "pwm"}
_INPUT_MODES = {"input", "input_analog"}


class SimulatedGPIOBackend(GPIOBackend):
    """
    Implementação de GPIOBackend que não toca hardware nenhum.

    Estrutura interna por pino:
        {
            "mode": "input" | "output" | "pwm" | "input_analog",
            "value": Any,       # último valor lido ou aplicado
            "config": {...},    # kwargs extras passados em setup()
        }
    """

    def __init__(self) -> None:
        self._pins: Dict[int, Dict[str, Any]] = {}

    def setup(self, pin: int, mode: str, **kwargs: Any) -> None:
        if mode not in _VALID_MODES:
            raise ValueError(
                f"Modo inválido '{mode}' para pino {pin}. "
                f"Esperado um de: {sorted(_VALID_MODES)}"
            )

        initial_value = kwargs.pop("initial_value", None)
        if initial_value is None:
            initial_value = False if mode in ("input", "output") else 0.0

        self._pins[pin] = {
            "mode": mode,
            "value": initial_value,
            "config": kwargs,
        }
        logger.info(
            "setup: pino=%s mode=%s initial_value=%s config=%s",
            pin, mode, initial_value, kwargs,
        )

    def read(self, pin: int) -> Any:
        state = self._require_pin(pin)
        value = state["value"]
        logger.debug("read: pino=%s mode=%s value=%s", pin, state["mode"], value)
        return value

    def write(self, pin: int, value: Any) -> None:
        state = self._require_pin(pin)
        mode = state["mode"]
        if mode not in _OUTPUT_MODES:
            raise ValueError(
                f"write() chamado em pino {pin} com mode='{mode}', "
                f"mas write só é permitido em modos {sorted(_OUTPUT_MODES)}. "
                f"Pinos de entrada são alterados via inject(), nunca via write()."
            )
        state["value"] = value
        logger.info("write: pino=%s mode=%s value=%s", pin, mode, value)

    def teardown(self, pin: int) -> None:
        if pin in self._pins:
            logger.info("teardown: pino=%s", pin)
            del self._pins[pin]

    def inject(self, pin: int, value: Any) -> None:
        """
        Injeta um valor "fake" em um pino de entrada (sensor simulado).

        Usado por testes e pelo painel web — nunca pelo bridge.py em
        operação normal, já que em hardware real esse valor viria do
        sensor físico via read().

        Diferente de write(), inject() é permitido apenas em pinos de
        modo "input"/"input_analog" — o inverso de write().
        """
        state = self._require_pin(pin)
        mode = state["mode"]
        if mode not in _INPUT_MODES:
            raise ValueError(
                f"inject() chamado em pino {pin} com mode='{mode}', "
                f"mas inject só é permitido em modos {sorted(_INPUT_MODES)}. "
                f"Pinos de saída são alterados via write()."
            )
        state["value"] = value
        logger.info("inject: pino=%s mode=%s value=%s", pin, mode, value)

    def snapshot(self) -> Dict[int, Dict[str, Any]]:
        """
        Retorna uma cópia do estado atual de todos os pinos configurados.
        Usado pelo painel web para listar o estado de todos os devices
        de uma vez, sem expor a estrutura interna mutável.
        """
        return {
            pin: {"mode": s["mode"], "value": s["value"], "config": dict(s["config"])}
            for pin, s in self._pins.items()
        }

    def _require_pin(self, pin: int) -> Dict[str, Any]:
        if pin not in self._pins:
            raise KeyError(
                f"Pino {pin} não foi configurado via setup() antes do uso."
            )
        return self._pins[pin]
