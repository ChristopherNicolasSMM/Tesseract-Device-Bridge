"""
Time-proportioning control — traduz um duty cycle desejado (0-100%) em
comandos liga/desliga distribuídos dentro de uma janela de tempo fixa,
para SSRs sem controle de fase analógico (caso real: as saídas NPN
digital da interface CraftBeerPi/MAZZA).

Exemplo: janela de 10s, duty_cycle=65% -> liga nos primeiros 6.5s da
janela, desliga nos 3.5s restantes, repete a cada nova janela.

Infraestrutura de hardware, não exclusiva de receita — usada por
`DeviceRuntime` (dono único por atuador, ver `hardware.window_seconds`
em `devices.yml`) tanto para o duty vindo do PID de uma receita ativa
quanto para o override manual (painel/comando individual). O
`RecipeEngine` não instancia mais este controller diretamente; ele só
pede um duty via `DeviceRuntime.set_pid_duty()`.

`now` é sempre recebido por parâmetro (nunca lido internamente via
time.time()) — mesma convenção do failsafe_watchdog.py, pra ser
testável sem sleep real.
"""

from __future__ import annotations


class TimeProportioningController:
    """
    :param window_seconds: duração da janela de tempo (recomendação
        prática: 5-15s para resistências de brassagem — janelas muito
        curtas desgastam o SSR/contator mecânico à toa, janelas muito
        longas perdem responsividade).
    """

    def __init__(self, window_seconds: float) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds deve ser > 0.")
        self._window_seconds = window_seconds
        self._duty_cycle_percent = 0.0
        self._window_start: float | None = None

    def set_duty_cycle(self, duty_cycle_percent: float) -> None:
        """
        Atualiza a potência desejada (0-100%) — normalmente chamado a
        cada ciclo do PID. Não afeta a janela em andamento, só o
        cálculo de liga/desliga nas próximas chamadas a should_be_on().
        """
        self._duty_cycle_percent = max(0.0, min(100.0, duty_cycle_percent))

    @property
    def duty_cycle_percent(self) -> float:
        """Última potência (0-100%) recebida via set_duty_cycle() — usado pela UI para o medidor."""
        return self._duty_cycle_percent

    def should_be_on(self, now: float) -> bool:
        """
        Decide se o relé deve estar ligado neste instante, dado o duty
        cycle atual e a posição dentro da janela. Avança a janela
        automaticamente quando o tempo decorrido ultrapassa
        window_seconds.
        """
        if self._window_start is None:
            self._window_start = now

        elapsed = now - self._window_start
        if elapsed >= self._window_seconds:
            # Nova janela — realinha o início, não acumula atraso.
            self._window_start = now
            elapsed = 0.0

        on_duration = self._window_seconds * (self._duty_cycle_percent / 100.0)
        return elapsed < on_duration

    def reset(self) -> None:
        """
        Reinicia o ciclo de janela — usado ao retomar de uma pausa, pra
        não começar uma janela "no meio" com base num now() antigo.
        """
        self._window_start = None
        self._duty_cycle_percent = 0.0
