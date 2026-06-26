"""
Interface abstrata para backends de GPIO.

Qualquer implementação concreta (real ou simulada) deve seguir este
contrato. O restante do sistema (bridge.py, panel/) nunca deve importar
RealGPIOBackend ou SimulatedGPIOBackend diretamente — sempre recebe uma
instância de GPIOBackend já resolvida pela configuração (devices.yml,
campo `backend`).
"""

from abc import ABC, abstractmethod
from typing import Any


class GPIOBackend(ABC):
    """
    Contrato comum entre RealGPIOBackend e SimulatedGPIOBackend.

    Um "pino" aqui é identificado pelo número físico (`pin`) declarado em
    `hardware.pin` no devices.yml. O backend não conhece o conceito de
    "device" (sensor/atuador) — isso é responsabilidade de bridge.py, que
    traduz device <-> pino antes de chamar o backend.
    """

    @abstractmethod
    def setup(self, pin: int, mode: str, **kwargs: Any) -> None:
        """
        Prepara um pino para uso.

        :param pin: número do pino (corresponde a `hardware.pin` no YAML).
        :param mode: "input" (sensor digital), "output" (atuador digital),
            "pwm" (atuador analógico/PWM), "input_analog" (sensor analógico,
            ex.: leitura de termistor/ADC).
        :param kwargs: parâmetros extras específicos do tipo de pino, ex.:
            `pwm_frequency` para mode="pwm" (mesmo nome de chave usado no
            devices.yml, em `hardware.pwm_frequency`).
        """
        raise NotImplementedError

    @abstractmethod
    def read(self, pin: int) -> Any:
        """
        Lê o valor atual de um pino já configurado via `setup()`.

        Retorno depende do mode: bool para "input", float para
        "input_analog"/"pwm" (estado aplicado), conforme o tipo configurado.
        """
        raise NotImplementedError

    @abstractmethod
    def write(self, pin: int, value: Any) -> None:
        """
        Aplica um valor a um pino de saída ("output" ou "pwm").

        Chamar write() em um pino configurado como "input"/"input_analog"
        deve levantar ValueError — backend nunca silencia esse erro.
        """
        raise NotImplementedError

    @abstractmethod
    def teardown(self, pin: int) -> None:
        """
        Libera um pino previamente configurado (ex.: ao desativar um
        device em runtime, ou no shutdown do bridge).
        """
        raise NotImplementedError
