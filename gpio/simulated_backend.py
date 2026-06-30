"""
Backend simulado de GPIO.

Mantém o estado de cada pino em memória (sem nenhuma dependência de
hardware), loga toda escrita/leitura, e permite injetar valores "fake"
de sensor via `inject()` — usado tanto em testes automatizados quanto
pelo painel web (quando o usuário ajusta um slider de sensor simulado).

Roda em qualquer máquina (Windows/Mac/Linux/Pi), sem nenhuma lib de
hardware instalada.

Suporta múltiplos devices no mesmo `pin`, desambiguados por `address`
(caso real: vários sensores DS18B20 no mesmo barramento 1-Wire) — chave
interna é `pin` quando `address` é None (comportamento idêntico ao de
antes desta extensão), ou `(pin, address)` quando presente.
"""

import logging
from typing import Any, Dict, Optional, Union

from gpio.base import GPIOBackend

logger = logging.getLogger("tesseract_bridge.gpio.simulated")

_VALID_MODES = {"input", "output", "pwm", "input_analog"}
_OUTPUT_MODES = {"output", "pwm"}
_INPUT_MODES = {"input", "input_analog"}

_Key = Union[int, "tuple[int, str]"]


def _make_key(pin: int, address: Optional[str]) -> _Key:
    return pin if address is None else (pin, address)


class SimulatedGPIOBackend(GPIOBackend):
    """
    Implementação de GPIOBackend que não toca hardware nenhum.

    Estrutura interna por chave (pin, ou (pin, address) se compartilhado):
        {
            "mode": "input" | "output" | "pwm" | "input_analog",
            "value": Any,       # último valor lido ou aplicado
            "config": {...},    # kwargs extras passados em setup()
        }
    """

    def __init__(self) -> None:
        self._pins: Dict[_Key, Dict[str, Any]] = {}

    def setup(self, pin: int, mode: str, **kwargs: Any) -> None:
        if mode not in _VALID_MODES:
            raise ValueError(
                f"Modo inválido '{mode}' para pino {pin}. "
                f"Esperado um de: {sorted(_VALID_MODES)}"
            )

        address = kwargs.pop("address", None)
        initial_value = kwargs.pop("initial_value", None)
        if initial_value is None:
            initial_value = False if mode in ("input", "output") else 0.0

        key = _make_key(pin, address)
        self._pins[key] = {
            "mode": mode,
            "value": initial_value,
            "config": kwargs,
        }
        logger.info(
            "setup: pino=%s address=%s mode=%s initial_value=%s config=%s",
            pin, address, mode, initial_value, kwargs,
        )

    def read(self, pin: int, address: Optional[str] = None) -> Any:
        state = self._require_pin(pin, address)
        value = state["value"]
        logger.debug("read: pino=%s address=%s mode=%s value=%s", pin, address, state["mode"], value)
        return value

    def write(self, pin: int, value: Any, address: Optional[str] = None) -> None:
        state = self._require_pin(pin, address)
        mode = state["mode"]
        if mode not in _OUTPUT_MODES:
            raise ValueError(
                f"write() chamado em pino {pin} com mode='{mode}', "
                f"mas write só é permitido em modos {sorted(_OUTPUT_MODES)}. "
                f"Pinos de entrada são alterados via inject(), nunca via write()."
            )
        state["value"] = value
        logger.info("write: pino=%s address=%s mode=%s value=%s", pin, address, mode, value)

    def teardown(self, pin: int, address: Optional[str] = None) -> None:
        key = _make_key(pin, address)
        if key in self._pins:
            logger.info("teardown: pino=%s address=%s", pin, address)
            del self._pins[key]

    def inject(self, pin: int, value: Any, address: Optional[str] = None) -> None:
        """
        Injeta um valor "fake" em um pino de entrada (sensor simulado).

        Usado por testes e pelo painel web — nunca pelo bridge.py em
        operação normal, já que em hardware real esse valor viria do
        sensor físico via read().

        Diferente de write(), inject() é permitido apenas em pinos de
        modo "input"/"input_analog" — o inverso de write().
        """
        state = self._require_pin(pin, address)
        mode = state["mode"]
        if mode not in _INPUT_MODES:
            raise ValueError(
                f"inject() chamado em pino {pin} com mode='{mode}', "
                f"mas inject só é permitido em modos {sorted(_INPUT_MODES)}. "
                f"Pinos de saída são alterados via write()."
            )
        state["value"] = value
        logger.info("inject: pino=%s address=%s mode=%s value=%s", pin, address, mode, value)

    def snapshot(self) -> Dict[_Key, Dict[str, Any]]:
        """
        Retorna uma cópia do estado atual de todos os pinos configurados.
        Usado pelo painel web para listar o estado de todos os devices
        de uma vez, sem expor a estrutura interna mutável. Chave é `pin`
        (int) para devices comuns, ou `(pin, address)` para devices em
        barramento compartilhado.
        """
        return {
            key: {"mode": s["mode"], "value": s["value"], "config": dict(s["config"])}
            for key, s in self._pins.items()
        }

    def _require_pin(self, pin: int, address: Optional[str]) -> Dict[str, Any]:
        key = _make_key(pin, address)
        if key not in self._pins:
            suffix = f" (address={address})" if address is not None else ""
            raise KeyError(
                f"Pino {pin}{suffix} não foi configurado via setup() antes do uso."
            )
        return self._pins[key]
