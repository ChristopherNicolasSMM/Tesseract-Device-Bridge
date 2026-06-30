"""
Interface abstrata para backends de GPIO.

Qualquer implementação concreta (real ou simulada) deve seguir este
contrato. O restante do sistema (bridge.py, panel/) nunca deve importar
RealGPIOBackend ou SimulatedGPIOBackend diretamente — sempre recebe uma
instância de GPIOBackend já resolvida pela configuração (devices.yml,
campo `backend`).
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class GPIOBackend(ABC):
    """
    Contrato comum entre RealGPIOBackend e SimulatedGPIOBackend.

    Um "pino" aqui é identificado pelo número físico (`pin`) declarado em
    `hardware.pin` no devices.yml. O backend não conhece o conceito de
    "device" (sensor/atuador) — isso é responsabilidade de bridge.py, que
    traduz device <-> pino antes de chamar o backend.

    `address` (opcional) desambigua múltiplos devices compartilhando o
    mesmo `pin` — caso real: vários sensores DS18B20 no mesmo barramento
    1-Wire, cada um identificado por seu endereço ROM único
    (`hardware.address` no devices.yml), não pelo pino (todos usam o
    mesmo GPIO4 fisicamente). Quando `address` é None (caso comum, 1
    pino = 1 device), o comportamento é idêntico ao de antes desta
    extensão.
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
            devices.yml, em `hardware.pwm_frequency`); `address` quando o
            pino é compartilhado entre múltiplos devices (barramento
            1-Wire) — extraído de `hardware.address` pelo chamador.
        """
        raise NotImplementedError

    @abstractmethod
    def read(self, pin: int, address: Optional[str] = None) -> Any:
        """
        Lê o valor atual de um pino (e, se aplicável, device específico
        dentro de um barramento compartilhado) já configurado via
        `setup()`.

        Retorno depende do mode: bool para "input", float para
        "input_analog"/"pwm" (estado aplicado), conforme o tipo configurado.
        """
        raise NotImplementedError

    @abstractmethod
    def write(self, pin: int, value: Any, address: Optional[str] = None) -> None:
        """
        Aplica um valor a um pino de saída ("output" ou "pwm").

        Chamar write() em um pino configurado como "input"/"input_analog"
        deve levantar ValueError — backend nunca silencia esse erro.
        """
        raise NotImplementedError

    @abstractmethod
    def teardown(self, pin: int, address: Optional[str] = None) -> None:
        """
        Libera um pino (e device específico, se aplicável) previamente
        configurado (ex.: ao desativar um device em runtime, ou no
        shutdown do bridge).
        """
        raise NotImplementedError
