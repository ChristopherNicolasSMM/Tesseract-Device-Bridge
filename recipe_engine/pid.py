"""
Controlador PID genérico, com anti-windup por clamping e saída
limitada a [0, 100] (percentual de potência) — usado pelo recipe_engine
(próxima fase) para controlar mash_heater/boil_heater via
time-proportioning (ver time_proportioning.py).

Implementação clássica de PID posicional, discreto, com `dt` explícito
por chamada (nunca lê relógio internamente) — torna o controlador
100% determinístico e testável sem sleep real.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PidGains:
    kp: float
    ki: float
    kd: float


class PidController:
    """
    :param gains: ganhos Kp/Ki/Kd.
    :param output_min: limite inferior da saída (default 0, percentual).
    :param output_max: limite superior da saída (default 100, percentual).
    """

    def __init__(self, gains: PidGains, output_min: float = 0.0, output_max: float = 100.0) -> None:
        if output_min >= output_max:
            raise ValueError("output_min deve ser menor que output_max.")
        self._gains = gains
        self._output_min = output_min
        self._output_max = output_max
        self._integral = 0.0
        self._previous_error: float | None = None

    def reset(self) -> None:
        """
        Zera o estado acumulado (integral, erro anterior) — usado ao
        iniciar uma nova etapa de receita ou ao retomar de uma pausa,
        pra não herdar acúmulo de uma situação anterior não relacionada.
        """
        self._integral = 0.0
        self._previous_error = None

    def compute(self, setpoint: float, current_value: float, dt: float) -> float:
        """
        Calcula a saída do PID para o instante atual.

        :param setpoint: temperatura alvo.
        :param current_value: temperatura medida agora.
        :param dt: tempo em segundos desde a última chamada a compute()
            (sempre passado explicitamente, nunca lido de relógio interno).
        :return: saída no intervalo [output_min, output_max].
        """
        if dt <= 0:
            raise ValueError(f"dt deve ser > 0, recebido {dt}.")

        error = setpoint - current_value

        # Anti-windup: só acumula integral se a saída não estiver
        # saturada na direção que pioraria o windup (clamping simples,
        # suficiente para o caso de uso de aquecimento — não há
        # necessidade de back-calculation mais sofisticado aqui).
        tentative_integral = self._integral + error * dt
        derivative = 0.0 if self._previous_error is None else (error - self._previous_error) / dt

        output_unclamped = (
            self._gains.kp * error
            + self._gains.ki * tentative_integral
            + self._gains.kd * derivative
        )

        if self._output_min <= output_unclamped <= self._output_max:
            self._integral = tentative_integral

        output = max(self._output_min, min(self._output_max, output_unclamped))

        self._previous_error = error
        return output
