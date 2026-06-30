"""
RecipeEngine — motor de execução de receita, 100% autônomo (não
depende de MQTT/Tesseract), com PID + time-proportioning por vasilha.

Convenção de tempo: `now` é sempre recebido por parâmetro em todo
método público — nunca lido internamente via time.time(). Isso torna
o motor inteiro determinístico e testável sem sleep real (mesma
convenção de failsafe_watchdog.py e time_proportioning.py).

Recuperação de crash (decisão registrada): se o processo cair (ou for
encerrado) no meio de uma execução (status "ramping"/"holding"), o
construtor detecta isso ao carregar o estado persistido, aplica
failsafe em todos os atuadores de risco do devices.yml inteiro
(segurança ampla, não só os da receita atual) e marca o estado como
"paused_after_crash" — nunca retoma sozinho, só por chamada explícita
a resume().
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Set

from device_runtime import DeviceRuntime
from recipe_engine.models import Recipe
from recipe_engine.pid import PidController
from recipe_engine.state import RecipeState
from recipe_engine.time_proportioning import TimeProportioningController


class RecipeEngineError(RuntimeError):
    """Erro de uso do RecipeEngine — ex.: ação incompatível com o status atual."""


class RecipeEngine:
    def __init__(
        self,
        runtime: DeviceRuntime,
        recipe: Recipe,
        state_path: str | Path,
        now: float,
    ) -> None:
        self._runtime = runtime
        self._recipe = recipe
        self._state_path = Path(state_path)
        self._state = RecipeState.load(self._state_path)

        self._pid: Dict[str, PidController] = {
            name: PidController(v.pid) for name, v in recipe.vessels.items()
        }
        self._tpc: Dict[str, TimeProportioningController] = {
            name: TimeProportioningController(v.window_seconds) for name, v in recipe.vessels.items()
        }
        self._active_pumps: Set[str] = set()
        self._last_tick_time: Optional[float] = None

        if self._state.status in ("ramping", "holding"):
            self._recover_from_crash(now)

    @property
    def state(self) -> RecipeState:
        return self._state

    @property
    def recipe_name(self) -> str:
        """Nome da receita carregada nesta engine, independente do status de execução."""
        return self._recipe.name

    # ---- ações de usuário -------------------------------------------------

    def start(self, now: float) -> None:
        """
        Inicia (ou reinicia do zero) a execução da receita carregada,
        independente do status atual — ação explícita do usuário, sempre
        permitida.
        """
        self._state = RecipeState.fresh(self._recipe.name)
        self._state.step_started_at = now
        self._reset_controllers_for_current_step()
        self._active_pumps = set()
        self._last_tick_time = None
        self._save()

    def abort(self, now: float) -> None:
        """
        Cancela a execução manualmente: aplica failsafe em tudo, status
        vira "aborted". Permitido em qualquer status — inclusive já
        idle/finished (vira no-op seguro nesse caso, sem erro).
        """
        self._apply_failsafe_all()
        self._active_pumps = set()
        self._state.status = "aborted"
        self._save()

    def resume(self, now: float) -> None:
        """
        Retoma uma execução pausada por crash, de onde parou — preserva
        o tempo de patamar já decorrido se a pausa ocorreu durante
        "holding". Único jeito de sair de "paused_after_crash".
        """
        if self._state.status != "paused_after_crash":
            raise RecipeEngineError(
                f"resume() só é válido em status 'paused_after_crash', atual é '{self._state.status}'."
            )

        self._reset_controllers_for_current_step()
        self._active_pumps = set()
        self._last_tick_time = None

        if self._state.paused_from_status == "holding":
            self._state.status = "holding"
            self._state.hold_started_at = now - self._state.hold_elapsed_seconds_at_pause
        else:
            self._state.status = "ramping"
            self._state.step_started_at = now
            self._state.hold_started_at = None

        self._state.paused_from_status = None
        self._save()

    # ---- loop principal -----------------------------------------------------

    def tick(self, now: float) -> None:
        """
        Avança o motor um passo — chamado periodicamente pelo loop do
        bridge (mesmo poll_interval usado por publish_sensor_states/
        check_watchdog). No-op se status não for "ramping"/"holding".
        """
        if self._state.status not in ("ramping", "holding"):
            return

        if self._last_tick_time is None:
            # Primeira chamada após start/resume: só estabelece o
            # relógio, sem calcular PID com dt inválido.
            self._last_tick_time = now
            return

        dt = now - self._last_tick_time
        self._last_tick_time = now
        if dt <= 0:
            return  # relógio não avançou (ou andou pra trás) — ignora este tick

        step = self._recipe.steps[self._state.step_index]
        vessel = self._recipe.vessels[step.vessel]

        self._apply_pumps(step.pumps)
        self._apply_heater(step, vessel, now, dt)

        if self._state.status == "ramping":
            current_temp = self._runtime.get_state(vessel.sensor_device_id).value
            if current_temp >= step.target_temp:
                self._state.status = "holding"
                self._state.hold_started_at = now
                self._save()

        elif self._state.status == "holding":
            elapsed = now - self._state.hold_started_at
            if elapsed >= step.hold_minutes * 60.0:
                self._advance_step(now)

    # ---- internos -------------------------------------------------------

    def _apply_heater(self, step, vessel, now: float, dt: float) -> None:
        current_temp = self._runtime.get_state(vessel.sensor_device_id).value
        pid = self._pid[step.vessel]
        tpc = self._tpc[step.vessel]
        duty = pid.compute(setpoint=step.target_temp, current_value=current_temp, dt=dt)
        tpc.set_duty_cycle(duty)
        heater_on = tpc.should_be_on(now)
        self._runtime.set_actuator(vessel.heater_device_id, heater_on)

    def _apply_pumps(self, desired_pump_ids) -> None:
        desired: Set[str] = set(desired_pump_ids)
        for pump_id in desired - self._active_pumps:
            self._runtime.set_actuator(pump_id, True)
        for pump_id in self._active_pumps - desired:
            self._runtime.set_actuator(pump_id, False)
        self._active_pumps = desired

    def _advance_step(self, now: float) -> None:
        current_step = self._recipe.steps[self._state.step_index]
        current_vessel = self._recipe.vessels[current_step.vessel]
        self._runtime.set_actuator(current_vessel.heater_device_id, False)

        next_index = self._state.step_index + 1
        if next_index >= self._recipe.step_count():
            self._apply_pumps([])
            self._state.status = "finished"
            self._state.hold_started_at = None
            self._save()
            return

        self._state.step_index = next_index
        self._state.status = "ramping"
        self._state.step_started_at = now
        self._state.hold_started_at = None
        next_step = self._recipe.steps[next_index]
        self._pid[next_step.vessel].reset()
        self._tpc[next_step.vessel].reset()
        self._apply_pumps(next_step.pumps)
        self._save()

    def _reset_controllers_for_current_step(self) -> None:
        if self._state.step_index < self._recipe.step_count():
            step = self._recipe.steps[self._state.step_index]
            self._pid[step.vessel].reset()
            self._tpc[step.vessel].reset()

    def _apply_failsafe_all(self) -> None:
        for device in self._runtime.list_device_configs():
            if device.is_risk:
                self._runtime.apply_failsafe(device.id)

    def _recover_from_crash(self, now: float) -> None:
        elapsed_hold = 0.0
        if self._state.status == "holding" and self._state.hold_started_at is not None:
            elapsed_hold = max(0.0, now - self._state.hold_started_at)

        self._state.paused_from_status = self._state.status
        self._state.hold_elapsed_seconds_at_pause = elapsed_hold
        self._state.status = "paused_after_crash"
        self._apply_failsafe_all()
        self._save()

    def _save(self) -> None:
        self._state.save(self._state_path)
