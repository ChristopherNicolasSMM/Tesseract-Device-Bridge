"""
RecipeEngine - motor de execucao de receita, 100% autonomo (nao
depende de MQTT/Tesseract), com PID + time-proportioning por vasilha.

Convencao de tempo: `now` e sempre recebido por parametro em todo
metodo publico - nunca lido internamente via time.time(). Isso torna
o motor inteiro deterministico e testavel sem sleep real (mesma
convencao de failsafe_watchdog.py e time_proportioning.py).

Recuperacao de crash (decisao registrada): se o processo cair (ou for
encerrado) no meio de uma execucao (status "ramping"/"holding"), o
construtor detecta isso ao carregar o estado persistido, aplica
failsafe em todos os atuadores de risco do devices.yml inteiro
(seguranca ampla, nao so os da receita atual) e marca o estado como
"paused_after_crash" - nunca retoma sozinho, so por chamada explicita
a resume().

Controles manuais (Sessao A): pause()/resume() (pausa deliberada pelo
usuario, mesma mecanica de aplicar failsafe + esperar confirmacao que
o crash recovery usa, mas via "paused_manual"), skip_next()/
skip_previous() (avanca/retrocede etapa manualmente, ignorando
temperatura/tempo), reset_current_step() (reinicia a etapa atual do
zero sem mudar de etapa).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Set

from device_runtime import DeviceRuntime
from recipe_engine.models import Recipe
from recipe_engine.pid import PidController
from recipe_engine.state import (
    ACTIVE_STATUSES,
    ALARM_TYPE_HOP_ADDITION,
    ALARM_TYPE_VESSEL_END,
    ALARM_TYPE_VESSEL_START,
    PAUSED_STATUSES,
    AlarmEvent,
    RecipeState,
)
from recipe_engine.time_proportioning import TimeProportioningController


class RecipeEngineError(RuntimeError):
    """Erro de uso do RecipeEngine - ex.: acao incompativel com o status atual."""


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
            v.id: PidController(v.pid) for v in recipe.vessels
        }
        self._tpc: Dict[str, TimeProportioningController] = {
            v.id: TimeProportioningController(v.window_seconds) for v in recipe.vessels
        }
        self._active_pumps: Set[str] = set()
        self._last_tick_time: Optional[float] = None

        if self._state.status in ACTIVE_STATUSES:
            self._recover_from_crash(now)

    @property
    def state(self) -> RecipeState:
        return self._state

    @property
    def recipe_name(self) -> str:
        """Nome da receita carregada nesta engine, independente do status de execucao."""
        return self._recipe.name

    @property
    def recipe(self):
        """Definicao completa da receita carregada (somente leitura)."""
        return self._recipe

    def current_duty(self, vessel_name: str) -> float:
        """Potencia atual (0-100%) calculada pelo PID para a vasilha - usado pela UI (medidor)."""
        if vessel_name not in self._tpc:
            return 0.0
        return self._tpc[vessel_name].duty_cycle_percent

    def total_estimated_minutes(self) -> float:
        """Soma de hold_minutes de todas as etapas - tempo previsto total da receita (sem contar rampa, que nao tem duracao previsivel)."""
        return sum(s.hold_minutes for s in self._recipe.steps)

    def total_elapsed_seconds(self, now: float) -> float:
        """
        Tempo total decorrido desde o inicio da execucao (start()), em
        segundos. Congelado (nao avanca mais) apos finished/aborted -
        usa o snapshot tirado no momento da transicao. Zero se a
        receita nunca foi iniciada (idle).
        """
        if self._state.status in ("finished", "aborted"):
            return self._state.total_elapsed_seconds_frozen or 0.0
        if self._state.recipe_started_at is None:
            return 0.0
        return max(0.0, now - self._state.recipe_started_at)

    @property
    def pending_alarms(self) -> list:
        """Alarmes disparados e ainda nao confirmados (popup + som no painel)."""
        return list(self._state.pending_alarms)

    def acknowledge_alarm(self, alarm_id: int) -> None:
        """Confirma (dispensa) um alarme pendente pelo id - remove da lista."""
        self._state.pending_alarms = [a for a in self._state.pending_alarms if a.id != alarm_id]
        self._save()

    # ---- acoes de usuario -------------------------------------------------

    def start(self, now: float) -> None:
        """
        Inicia (ou reinicia do zero) a execucao da receita carregada,
        independente do status atual - acao explicita do usuario, sempre
        permitida.
        """
        self._state = RecipeState.fresh(self._recipe.name)
        self._state.step_started_at = now
        self._state.recipe_started_at = now
        self._reset_controllers_for_current_step()
        self._active_pumps = set()
        self._last_tick_time = None
        first_step = self._recipe.steps[0]
        first_vessel = self._recipe.get_vessel(first_step.vessel)
        self._fire_alarm(ALARM_TYPE_VESSEL_START, f"Início {first_vessel.name}", now)
        self._save()

    def abort(self, now: float) -> None:
        """
        Cancela a execucao manualmente: aplica failsafe em tudo, status
        vira "aborted". Permitido em qualquer status - inclusive ja
        idle/finished (vira no-op seguro nesse caso, sem erro).
        """
        self._state.total_elapsed_seconds_frozen = self.total_elapsed_seconds(now)
        self._apply_failsafe_all()
        self._active_pumps = set()
        self._state.status = "aborted"
        self._save()

    def pause(self, now: float) -> None:
        """
        Pausa deliberada pelo usuario (botao no painel) - aplica
        failsafe em tudo (mesma seguranca do crash recovery) e marca
        "paused_manual". So valido durante ramping/holding.
        """
        if self._state.status not in ACTIVE_STATUSES:
            raise RecipeEngineError(
                f"pause() so e valido durante execucao ativa (ramping/holding), atual e '{self._state.status}'."
            )

        elapsed_hold = 0.0
        if self._state.status == "holding" and self._state.hold_started_at is not None:
            elapsed_hold = max(0.0, now - self._state.hold_started_at)

        self._state.paused_from_status = self._state.status
        self._state.hold_elapsed_seconds_at_pause = elapsed_hold
        self._state.status = "paused_manual"
        self._apply_failsafe_all()
        self._active_pumps = set()
        self._save()

    def resume(self, now: float) -> None:
        """
        Retoma uma execucao pausada (por crash OU pausa manual), de
        onde parou - preserva o tempo de patamar ja decorrido se a
        pausa ocorreu durante "holding". Unico jeito de sair de
        "paused_after_crash"/"paused_manual".
        """
        if self._state.status not in PAUSED_STATUSES:
            raise RecipeEngineError(
                f"resume() so e valido em status pausado ({sorted(PAUSED_STATUSES)}), atual e '{self._state.status}'."
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

    def skip_next(self, now: float) -> None:
        """
        Forca avanco pra proxima etapa, ignorando temperatura/tempo de
        patamar - mesmo efeito de completar a etapa atual naturalmente.
        So valido durante ramping/holding.
        """
        if self._state.status not in ACTIVE_STATUSES:
            raise RecipeEngineError(
                f"skip_next() so e valido durante execucao ativa, atual e '{self._state.status}'."
            )
        self._advance_step(now)

    def skip_previous(self, now: float) -> None:
        """
        Volta pra etapa anterior (reiniciando ela do zero - rampa de
        novo, ja que nao ha como saber o estado termico de um momento
        passado). Se ja estiver na primeira etapa, reinicia a etapa
        atual (equivalente a reset_current_step()). So valido durante
        ramping/holding.
        """
        if self._state.status not in ACTIVE_STATUSES:
            raise RecipeEngineError(
                f"skip_previous() so e valido durante execucao ativa, atual e '{self._state.status}'."
            )

        current_step = self._recipe.steps[self._state.step_index]
        current_vessel = self._recipe.get_vessel(current_step.vessel)
        self._runtime.set_actuator(current_vessel.heater_device_id, False)

        if self._state.step_index > 0:
            self._state.step_index -= 1

        self._restart_current_step(now)

    def reset_current_step(self, now: float) -> None:
        """
        Reinicia a etapa atual do zero (volta pra ramping, zera tempo
        de patamar), sem mudar de etapa - util pra "tentar de novo"
        sem perder o lugar na receita. So valido durante ramping/holding.
        """
        if self._state.status not in ACTIVE_STATUSES:
            raise RecipeEngineError(
                f"reset_current_step() so e valido durante execucao ativa, atual e '{self._state.status}'."
            )
        self._restart_current_step(now)

    # ---- loop principal -----------------------------------------------------

    def tick(self, now: float) -> None:
        """
        Avanca o motor um passo - chamado periodicamente pelo loop do
        bridge (mesmo poll_interval usado por publish_sensor_states/
        check_watchdog). No-op se status nao for "ramping"/"holding".
        """
        if self._state.status not in ACTIVE_STATUSES:
            return

        if self._last_tick_time is None:
            # Primeira chamada apos start/resume/skip: so estabelece o
            # relogio, sem calcular PID com dt invalido.
            self._last_tick_time = now
            return

        dt = now - self._last_tick_time
        self._last_tick_time = now
        if dt <= 0:
            return  # relogio nao avancou (ou andou pra tras) - ignora este tick

        step = self._recipe.steps[self._state.step_index]
        vessel = self._recipe.get_vessel(step.vessel)

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
            self._check_hop_alarms(step, elapsed, now)
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

    def _restart_current_step(self, now: float) -> None:
        self._state.status = "ramping"
        self._state.step_started_at = now
        self._state.hold_started_at = None
        self._last_tick_time = None
        self._state.fired_hop_alarm_keys = []
        step = self._recipe.steps[self._state.step_index]
        self._pid[step.vessel].reset()
        self._tpc[step.vessel].reset()
        self._apply_pumps(step.pumps)
        self._save()

    def _advance_step(self, now: float) -> None:
        current_step = self._recipe.steps[self._state.step_index]
        current_vessel = self._recipe.get_vessel(current_step.vessel)
        self._runtime.set_actuator(current_vessel.heater_device_id, False)

        next_index = self._state.step_index + 1
        if next_index >= self._recipe.step_count():
            self._apply_pumps([])
            self._state.total_elapsed_seconds_frozen = self.total_elapsed_seconds(now)
            self._state.status = "finished"
            self._state.hold_started_at = None
            self._fire_alarm(ALARM_TYPE_VESSEL_END, f"Final {current_vessel.name}", now)
            self._save()
            return

        next_step = self._recipe.steps[next_index]
        next_vessel = self._recipe.get_vessel(next_step.vessel)
        if next_vessel.id != current_vessel.id:
            self._fire_alarm(ALARM_TYPE_VESSEL_END, f"Final {current_vessel.name}", now)
            self._fire_alarm(ALARM_TYPE_VESSEL_START, f"Início {next_vessel.name}", now)

        self._state.step_index = next_index
        self._restart_current_step(now)

    def _reset_controllers_for_current_step(self) -> None:
        if self._state.step_index < self._recipe.step_count():
            step = self._recipe.steps[self._state.step_index]
            self._pid[step.vessel].reset()
            self._tpc[step.vessel].reset()

    def _apply_failsafe_all(self) -> None:
        for device in self._runtime.list_device_configs():
            if device.is_risk:
                self._runtime.apply_failsafe(device.id)

    def _fire_alarm(self, alarm_type: str, label: str, now: float) -> None:
        event = AlarmEvent(id=self._state.next_alarm_id, type=alarm_type, label=label, fired_at=now)
        self._state.pending_alarms.append(event)
        self._state.next_alarm_id += 1
        self._save()

    def _check_hop_alarms(self, step, hold_elapsed_seconds: float, now: float) -> None:
        hold_total_seconds = step.hold_minutes * 60.0
        remaining_seconds = hold_total_seconds - hold_elapsed_seconds
        for alarm_index, hop_alarm in enumerate(step.hop_alarms):
            key = f"{self._state.step_index}:{alarm_index}"
            if key in self._state.fired_hop_alarm_keys:
                continue
            if remaining_seconds <= hop_alarm.minutes_remaining * 60.0:
                self._state.fired_hop_alarm_keys.append(key)
                self._fire_alarm(ALARM_TYPE_HOP_ADDITION, hop_alarm.label, now)

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
