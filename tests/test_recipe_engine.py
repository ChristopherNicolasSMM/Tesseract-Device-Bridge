import textwrap

import pytest

from config import BridgeConfig
from device_runtime import DeviceRuntime
from gpio.simulated_backend import SimulatedGPIOBackend
from recipe_engine.engine import RecipeEngine, RecipeEngineError
from recipe_engine.models import Recipe
from recipe_engine.state import RecipeState


DEVICES_YAML = """
mqtt:
  enabled: false
backend: simulated
panel:
  enabled: false

devices:
  - id: mash_tun_temp
    name: "Temp Mostura"
    role: sensor
    subtype: temperature
    state_topic: "sensors/mash_tun_temp/state"
    hardware: { pin: 4, driver: ds18b20, address: "28-aaa" }
    simulated: { initial_value: 20.0 }

  - id: boil_temp
    name: "Temp Fervura"
    role: sensor
    subtype: temperature
    state_topic: "sensors/boil_temp/state"
    hardware: { pin: 4, driver: ds18b20, address: "28-bbb" }
    simulated: { initial_value: 20.0 }

  - id: mash_heater
    name: "Aquecedor Mostura"
    role: actuator
    subtype: digital
    command_topic: "actuators/mash_heater/set"
    hardware: { pin: 17, window_seconds: 10 }
    failsafe_value: false
    is_risk: true
    failsafe_timeout_seconds: 30

  - id: boil_heater
    name: "Aquecedor Fervura"
    role: actuator
    subtype: digital
    command_topic: "actuators/boil_heater/set"
    hardware: { pin: 27, window_seconds: 10 }
    failsafe_value: false
    is_risk: true
    failsafe_timeout_seconds: 30

  - id: pump_b1
    name: "Bomba B1"
    role: actuator
    subtype: digital
    command_topic: "actuators/pump_b1/set"
    hardware: { pin: 22 }
    failsafe_value: false
    is_risk: true
    failsafe_timeout_seconds: 30
"""

RECIPE_YAML = """
name: "Receita Teste"
vessels:
  - id: mash
    name: "Mash"
    heater_device_id: mash_heater
    sensor_device_id: mash_tun_temp
    pid: { kp: 50.0, ki: 0.0, kd: 0.0 }
  - id: boil
    name: "Boil"
    heater_device_id: boil_heater
    sensor_device_id: boil_temp
    pid: { kp: 50.0, ki: 0.0, kd: 0.0 }
steps:
  - vessel: mash
    target_temp: 25.0
    hold_minutes: 1
    pumps: [pump_b1]
  - vessel: boil
    target_temp: 30.0
    hold_minutes: 1
"""


@pytest.fixture
def setup(tmp_path):
    devices_path = tmp_path / "devices.yml"
    devices_path.write_text(textwrap.dedent(DEVICES_YAML), encoding="utf-8")
    bridge_config = BridgeConfig.load(devices_path)

    backend = SimulatedGPIOBackend()
    runtime = DeviceRuntime(bridge_config, backend)

    recipe_path = tmp_path / "recipe.yml"
    recipe_path.write_text(textwrap.dedent(RECIPE_YAML), encoding="utf-8")
    recipe = Recipe.load(recipe_path, bridge_config)

    state_path = tmp_path / "recipe_state.json"
    return runtime, recipe, state_path


def test_fresh_engine_starts_idle(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    assert engine.state.status == "idle"


def test_start_transitions_to_ramping(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    assert engine.state.status == "ramping"
    assert engine.state.step_index == 0


def test_tick_first_call_only_sets_clock_no_action(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.tick(now=1000.0)
    # sem dt válido ainda, heater não deveria ter sido acionado
    assert runtime.get_state("mash_heater").value is False


def test_tick_drives_heater_via_pid_during_ramping(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.tick(now=1000.0)  # estabelece relógio
    engine.tick(now=1001.0)  # primeiro cálculo de PID real

    # temp atual=20, setpoint=25, erro=5, kp=50 -> duty=100% (clampado) -> heater ligado
    assert runtime.get_state("mash_heater").value is True


def test_current_duty_reflects_pid_output(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    assert engine.current_duty("mash") == 0.0  # antes de qualquer tick

    engine.start(now=1000.0)
    engine.tick(now=1000.0)
    engine.tick(now=1001.0)
    assert engine.current_duty("mash") == 100.0  # erro grande, kp alto -> satura em 100%


def test_current_duty_unknown_vessel_returns_zero(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    assert engine.current_duty("does_not_exist") == 0.0


def test_tick_activates_step_pumps(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.tick(now=1000.0)
    engine.tick(now=1001.0)
    assert runtime.get_state("pump_b1").value is True


def test_apply_pumps_respects_manual_override_preventing_auto_on(setup):
    """
    Achado real: _apply_pumps() decide liga/desliga comparando com seu
    próprio bookkeeping (self._active_pumps), nunca com o estado físico.
    Sem checar has_manual_override(), um override manual seria ignorado
    silenciosamente assim que a etapa pedisse o pump ligado.
    """
    runtime, recipe, state_path = setup
    runtime.set_manual_override("pump_b1", False)  # override antes de iniciar

    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.tick(now=1000.0)
    engine.tick(now=1001.0)  # step0 pede pump_b1 ligado -- mas está sob override

    assert runtime.get_state("pump_b1").value is False


def test_apply_pumps_respects_manual_override_preventing_auto_off_on_transition(setup):
    """
    Cenário central do bug: pump ligado normalmente pela receita, usuário
    assume controle manual, receita avança de etapa (etapa nova não usa
    esse pump) -- sem o guard, o diff interno desligaria o pump sozinho,
    desfazendo o comando manual sem nenhum aviso.
    """
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.tick(now=1000.0)
    engine.tick(now=1001.0)
    assert runtime.get_state("pump_b1").value is True  # ligado normalmente pela receita

    runtime.set_manual_override("pump_b1", True)  # usuário assume controle

    engine.skip_next(now=1002.0)  # avança pra "boil", que não usa pump_b1

    assert runtime.get_state("pump_b1").value is True  # override impediu o desligamento automático


def test_ramping_transitions_to_holding_when_target_reached(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.tick(now=1000.0)

    runtime.inject_sensor("mash_tun_temp", 25.0)  # já bateu o alvo
    engine.tick(now=1001.0)

    assert engine.state.status == "holding"
    assert engine.state.hold_started_at == 1001.0


def test_holding_does_not_advance_before_hold_time_elapsed(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.tick(now=1000.0)
    runtime.inject_sensor("mash_tun_temp", 25.0)
    engine.tick(now=1001.0)  # entra em holding

    engine.tick(now=1030.0)  # só 29s de patamar (hold_minutes=1 -> 60s)
    assert engine.state.status == "holding"
    assert engine.state.step_index == 0


def test_holding_advances_to_next_step_after_hold_time(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.tick(now=1000.0)
    runtime.inject_sensor("mash_tun_temp", 25.0)
    engine.tick(now=1001.0)  # entra em holding (hold_started_at=1001)

    engine.tick(now=1062.0)  # 61s de patamar > 60s -> avança

    assert engine.state.step_index == 1
    assert engine.state.status == "ramping"
    # heater da etapa anterior deve ter sido desligado
    assert runtime.get_state("mash_heater").value is False
    # bomba da etapa anterior (só na etapa 0) deve ter sido desligada
    assert runtime.get_state("pump_b1").value is False


def test_finishing_last_step_sets_status_finished(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.tick(now=1000.0)
    runtime.inject_sensor("mash_tun_temp", 25.0)
    engine.tick(now=1001.0)
    engine.tick(now=1062.0)  # avança pra etapa 1 (boil)

    engine.tick(now=1063.0)  # estabelece relógio na nova etapa
    runtime.inject_sensor("boil_temp", 30.0)
    engine.tick(now=1064.0)  # holding na etapa 1

    engine.tick(now=1125.0)  # 61s de patamar -> última etapa, finished

    assert engine.state.status == "finished"
    assert runtime.get_state("boil_heater").value is False


def test_tick_is_noop_when_idle(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.tick(now=1001.0)  # nunca deu start()
    assert engine.state.status == "idle"
    assert runtime.get_state("mash_heater").value is False


def test_abort_applies_failsafe_and_sets_aborted(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.tick(now=1000.0)
    engine.tick(now=1001.0)  # heater ligado

    engine.abort(now=1002.0)

    assert engine.state.status == "aborted"
    assert runtime.get_state("mash_heater").value is False
    assert runtime.get_state("boil_heater").value is False
    assert runtime.get_state("pump_b1").value is False


def test_crash_recovery_on_construction_during_ramping(setup):
    runtime, recipe, state_path = setup
    engine1 = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine1.start(now=1000.0)
    engine1.tick(now=1000.0)
    engine1.tick(now=1001.0)  # heater ligado, status=ramping persistido
    assert runtime.get_state("mash_heater").value is True

    # Simula reinício do processo: nova engine, mesmo state_path, mesmo runtime.
    engine2 = RecipeEngine(runtime, recipe, state_path, now=1005.0)

    assert engine2.state.status == "paused_after_crash"
    assert engine2.state.paused_from_status == "ramping"
    # failsafe aplicado de verdade no runtime real
    assert runtime.get_state("mash_heater").value is False
    assert runtime.get_state("boil_heater").value is False


def test_crash_recovery_during_holding_preserves_elapsed_time(setup):
    runtime, recipe, state_path = setup
    engine1 = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine1.start(now=1000.0)
    engine1.tick(now=1000.0)
    runtime.inject_sensor("mash_tun_temp", 25.0)
    engine1.tick(now=1001.0)  # entra em holding, hold_started_at=1001
    assert engine1.state.status == "holding"

    # "crash" 20s depois de entrar em holding
    engine2 = RecipeEngine(runtime, recipe, state_path, now=1021.0)

    assert engine2.state.status == "paused_after_crash"
    assert engine2.state.paused_from_status == "holding"
    assert engine2.state.hold_elapsed_seconds_at_pause == pytest.approx(20.0)


def test_resume_from_ramping_crash_continues_correctly(setup):
    runtime, recipe, state_path = setup
    engine1 = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine1.start(now=1000.0)
    engine1.tick(now=1000.0)
    engine1.tick(now=1001.0)

    engine2 = RecipeEngine(runtime, recipe, state_path, now=1005.0)
    assert engine2.state.status == "paused_after_crash"

    engine2.resume(now=1010.0)
    assert engine2.state.status == "ramping"

    engine2.tick(now=1010.0)
    runtime.inject_sensor("mash_tun_temp", 25.0)
    engine2.tick(now=1011.0)
    assert engine2.state.status == "holding"


def test_resume_from_holding_crash_preserves_elapsed_hold_time(setup):
    runtime, recipe, state_path = setup
    engine1 = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine1.start(now=1000.0)
    engine1.tick(now=1000.0)
    runtime.inject_sensor("mash_tun_temp", 25.0)
    engine1.tick(now=1001.0)  # holding desde t=1001

    # crash em t=1021 (20s de holding já passados)
    engine2 = RecipeEngine(runtime, recipe, state_path, now=1021.0)
    assert engine2.state.hold_elapsed_seconds_at_pause == pytest.approx(20.0)

    # resume em t=1100 (bem depois)
    engine2.resume(now=1100.0)
    assert engine2.state.status == "holding"
    # hold_started_at deveria ser recalculado pra preservar os 20s já decorridos:
    # 1100 - hold_started_at == 20 -> hold_started_at == 1080
    assert engine2.state.hold_started_at == pytest.approx(1080.0)

    engine2.tick(now=1100.0)
    # faltam 40s pro patamar de 60s completar (60-20=40) a partir de t=1100
    engine2.tick(now=1135.0)  # +35s, ainda não completou (35 < 40)
    assert engine2.state.status == "holding"

    engine2.tick(now=1142.0)  # +42s totais (>40) -> avança
    assert engine2.state.step_index == 1


def test_resume_without_crash_raises_error(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    with pytest.raises(RecipeEngineError, match="paused_after_crash"):
        engine.resume(now=1001.0)


def test_start_works_from_finished_status(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.tick(now=1000.0)
    runtime.inject_sensor("mash_tun_temp", 25.0)
    engine.tick(now=1001.0)
    engine.tick(now=1062.0)
    engine.tick(now=1063.0)
    runtime.inject_sensor("boil_temp", 30.0)
    engine.tick(now=1064.0)
    engine.tick(now=1125.0)
    assert engine.state.status == "finished"

    engine.start(now=2000.0)
    assert engine.state.status == "ramping"
    assert engine.state.step_index == 0


def test_state_persists_across_engine_instances_without_crash_status(setup):
    """
    Reabrir a engine quando o estado salvo é 'finished' (encerramento
    normal, não crash) não deve disparar recovery nem failsafe.
    """
    runtime, recipe, state_path = setup
    engine1 = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine1.start(now=1000.0)
    engine1.tick(now=1000.0)
    runtime.inject_sensor("mash_tun_temp", 25.0)
    engine1.tick(now=1001.0)
    engine1.tick(now=1062.0)
    engine1.tick(now=1063.0)
    runtime.inject_sensor("boil_temp", 30.0)
    engine1.tick(now=1064.0)
    engine1.tick(now=1125.0)
    assert engine1.state.status == "finished"

    engine2 = RecipeEngine(runtime, recipe, state_path, now=2000.0)
    assert engine2.state.status == "finished"  # não virou paused_after_crash


# ---- Sessão A: pause/resume manual, skip, reset, tempo total ----------

def test_pause_applies_failsafe_and_sets_paused_manual(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.tick(now=1000.0)
    engine.tick(now=1001.0)  # heater ligado, bomba ligada

    engine.pause(now=1002.0)

    assert engine.state.status == "paused_manual"
    assert runtime.get_state("mash_heater").value is False
    assert runtime.get_state("pump_b1").value is False


def test_pause_outside_active_status_raises(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    with pytest.raises(RecipeEngineError):
        engine.pause(now=1001.0)  # ainda idle


def test_resume_from_manual_pause_during_ramping(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.tick(now=1000.0)
    engine.tick(now=1001.0)

    engine.pause(now=1002.0)
    assert engine.state.status == "paused_manual"

    engine.resume(now=1010.0)
    assert engine.state.status == "ramping"

    engine.tick(now=1010.0)
    runtime.inject_sensor("mash_tun_temp", 25.0)
    engine.tick(now=1011.0)
    assert engine.state.status == "holding"


def test_resume_from_manual_pause_during_holding_preserves_elapsed(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.tick(now=1000.0)
    runtime.inject_sensor("mash_tun_temp", 25.0)
    engine.tick(now=1001.0)  # holding desde t=1001
    assert engine.state.status == "holding"

    engine.pause(now=1021.0)  # pausado com 20s de patamar decorridos
    assert engine.state.hold_elapsed_seconds_at_pause == pytest.approx(20.0)

    engine.resume(now=1100.0)
    assert engine.state.status == "holding"
    assert engine.state.hold_started_at == pytest.approx(1080.0)  # 1100 - 20


def test_skip_next_advances_to_next_step_immediately(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.tick(now=1000.0)
    engine.tick(now=1001.0)  # ainda ramping, longe do alvo

    engine.skip_next(now=1002.0)

    assert engine.state.step_index == 1
    assert engine.state.status == "ramping"
    assert runtime.get_state("mash_heater").value is False  # heater anterior desligado


def test_skip_next_on_last_step_finishes_recipe(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.tick(now=1000.0)
    engine.tick(now=1001.0)
    engine.skip_next(now=1002.0)  # vai pra etapa 1 (boil, última)
    assert engine.state.step_index == 1

    engine.skip_next(now=1003.0)  # última etapa -> finished
    assert engine.state.status == "finished"


def test_skip_next_outside_active_status_raises(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    with pytest.raises(RecipeEngineError):
        engine.skip_next(now=1001.0)


def test_skip_previous_goes_back_one_step(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.tick(now=1000.0)
    engine.tick(now=1001.0)
    engine.skip_next(now=1002.0)  # etapa 1 (boil)
    assert engine.state.step_index == 1

    engine.skip_previous(now=1003.0)
    assert engine.state.step_index == 0
    assert engine.state.status == "ramping"


def test_skip_previous_at_first_step_restarts_it(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.tick(now=1000.0)
    runtime.inject_sensor("mash_tun_temp", 25.0)
    engine.tick(now=1001.0)  # holding

    engine.skip_previous(now=1002.0)
    assert engine.state.step_index == 0
    assert engine.state.status == "ramping"  # reiniciou a própria etapa


def test_skip_previous_turns_off_heater_of_step_being_left(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.tick(now=1000.0)
    engine.tick(now=1001.0)
    engine.skip_next(now=1002.0)  # etapa 1 (boil)
    engine.tick(now=1002.0)
    engine.tick(now=1003.0)  # boil_heater ligado

    engine.skip_previous(now=1004.0)
    assert runtime.get_state("boil_heater").value is False


def test_reset_current_step_restarts_without_changing_index(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.tick(now=1000.0)
    runtime.inject_sensor("mash_tun_temp", 25.0)
    engine.tick(now=1001.0)  # holding
    assert engine.state.status == "holding"

    engine.reset_current_step(now=1030.0)
    assert engine.state.step_index == 0
    assert engine.state.status == "ramping"
    assert engine.state.step_started_at == 1030.0


def test_reset_current_step_outside_active_status_raises(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    with pytest.raises(RecipeEngineError):
        engine.reset_current_step(now=1001.0)


def test_total_estimated_minutes_sums_all_steps(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    # RECIPE_YAML: 2 steps de hold_minutes=1 cada -> 2 minutos totais
    assert engine.total_estimated_minutes() == pytest.approx(2.0)


def test_total_elapsed_seconds_zero_when_idle(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    assert engine.total_elapsed_seconds(now=1500.0) == 0.0


def test_total_elapsed_seconds_live_while_running(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    assert engine.total_elapsed_seconds(now=1030.0) == pytest.approx(30.0)


def test_total_elapsed_seconds_frozen_after_abort(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.abort(now=1045.0)

    assert engine.total_elapsed_seconds(now=1045.0) == pytest.approx(45.0)
    # tempo "congela" -- chamar bem depois não muda o valor
    assert engine.total_elapsed_seconds(now=9999.0) == pytest.approx(45.0)


def test_total_elapsed_seconds_frozen_after_finish(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.tick(now=1000.0)
    runtime.inject_sensor("mash_tun_temp", 25.0)
    engine.tick(now=1001.0)
    engine.tick(now=1062.0)
    engine.tick(now=1063.0)
    runtime.inject_sensor("boil_temp", 30.0)
    engine.tick(now=1064.0)
    engine.tick(now=1125.0)
    assert engine.state.status == "finished"

    elapsed_at_finish = engine.total_elapsed_seconds(now=1125.0)
    assert engine.total_elapsed_seconds(now=9999.0) == elapsed_at_finish


# ---- Timers de alarme (vessel_start/end automaticos + hop_alarms) -----

ALARM_RECIPE_YAML = """
name: "Receita Com Alarmes"
vessels:
  - id: mash
    name: "Mostura"
    heater_device_id: mash_heater
    sensor_device_id: mash_tun_temp
    pid: { kp: 50.0, ki: 0.0, kd: 0.0 }
  - id: boil
    name: "Fervura"
    heater_device_id: boil_heater
    sensor_device_id: boil_temp
    pid: { kp: 50.0, ki: 0.0, kd: 0.0 }
steps:
  - vessel: mash
    target_temp: 25.0
    hold_minutes: 1
    pumps: [pump_b1]
  - vessel: mash
    target_temp: 25.0
    hold_minutes: 1
    pumps: [pump_b1]
  - vessel: boil
    target_temp: 30.0
    hold_minutes: 2
    hop_alarms:
      - minutes_remaining: 1.5
        label: "Lupulo Amargor"
      - minutes_remaining: 0
        label: "Whirlpool"
"""


@pytest.fixture
def alarm_setup(tmp_path):
    devices_path = tmp_path / "devices.yml"
    devices_path.write_text(textwrap.dedent(DEVICES_YAML), encoding="utf-8")
    bridge_config = BridgeConfig.load(devices_path)

    backend = SimulatedGPIOBackend()
    runtime = DeviceRuntime(bridge_config, backend)

    recipe_path = tmp_path / "recipe.yml"
    recipe_path.write_text(textwrap.dedent(ALARM_RECIPE_YAML), encoding="utf-8")
    recipe = Recipe.load(recipe_path, bridge_config)

    state_path = tmp_path / "recipe_state.json"
    return runtime, recipe, state_path


def test_start_fires_vessel_start_for_first_step(alarm_setup):
    runtime, recipe, state_path = alarm_setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)

    alarms = engine.pending_alarms
    assert len(alarms) == 1
    assert alarms[0].type == "vessel_start"
    assert alarms[0].label == "Início Mostura"


def test_no_vessel_alarm_between_two_steps_of_same_vessel(alarm_setup):
    runtime, recipe, state_path = alarm_setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.acknowledge_alarm(engine.pending_alarms[0].id)

    engine.tick(now=1000.0)
    runtime.inject_sensor("mash_tun_temp", 25.0)
    engine.tick(now=1001.0)  # holding
    engine.tick(now=1062.0)  # avanca pra step 1 (mash de novo, mesma vessel)

    assert engine.state.step_index == 1
    assert engine.pending_alarms == []  # sem transicao de vessel, sem alarme


def test_vessel_transition_fires_end_and_start(alarm_setup):
    runtime, recipe, state_path = alarm_setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.acknowledge_alarm(engine.pending_alarms[0].id)

    engine.tick(now=1000.0)
    runtime.inject_sensor("mash_tun_temp", 25.0)
    engine.tick(now=1001.0)
    engine.tick(now=1062.0)  # step 0 -> 1 (mash->mash, sem alarme)

    engine.tick(now=1063.0)  # estabelece relogio na step 1
    engine.tick(now=1064.0)  # temp ja em 25.0 (igual ao alvo) -> entra em holding aqui
    engine.tick(now=1125.0)  # 61s de patamar -> step 1 -> 2 (mash->boil, deve disparar end+start)

    alarms = engine.pending_alarms
    assert len(alarms) == 2
    assert alarms[0].type == "vessel_end"
    assert alarms[0].label == "Final Mostura"
    assert alarms[1].type == "vessel_start"
    assert alarms[1].label == "Início Fervura"


def test_finishing_recipe_fires_vessel_end(alarm_setup):
    runtime, recipe, state_path = alarm_setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.acknowledge_alarm(engine.pending_alarms[0].id)

    # avanca rapidamente ate o fim usando skip_next (nao dispara automatico por temperatura)
    engine.skip_next(now=1001.0)  # step0->1
    for a in list(engine.pending_alarms):
        engine.acknowledge_alarm(a.id)
    engine.skip_next(now=1002.0)  # step1->2 (mash->boil: end+start)
    for a in list(engine.pending_alarms):
        engine.acknowledge_alarm(a.id)
    engine.skip_next(now=1003.0)  # step2 (boil, ultima) -> finished

    alarms = engine.pending_alarms
    assert len(alarms) == 1
    assert alarms[0].type == "vessel_end"
    assert alarms[0].label == "Final Fervura"
    assert engine.state.status == "finished"


def test_hop_alarm_fires_when_remaining_time_crosses_threshold(alarm_setup):
    runtime, recipe, state_path = alarm_setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.acknowledge_alarm(engine.pending_alarms[0].id)
    engine.skip_next(now=1001.0)
    for a in list(engine.pending_alarms):
        engine.acknowledge_alarm(a.id)
    engine.skip_next(now=1002.0)  # agora na etapa boil (hold_minutes=2 -> 120s)
    for a in list(engine.pending_alarms):
        engine.acknowledge_alarm(a.id)

    runtime.inject_sensor("boil_temp", 30.0)
    engine.tick(now=1002.0)  # estabelece relogio
    engine.tick(now=1003.0)  # entra em holding (hold_started_at=1003)

    # hop_alarms: minutes_remaining=1.5 (90s) e 0 (0s), hold_total=120s
    # com 20s decorridos, faltam 100s -> ainda nao deveria disparar o de 90s
    engine.tick(now=1023.0)
    assert engine.pending_alarms == []

    # com 35s decorridos, faltam 85s (<=90s) -> dispara o alarme de 90s
    engine.tick(now=1038.0)
    alarms = engine.pending_alarms
    assert len(alarms) == 1
    assert alarms[0].type == "hop_addition"
    assert alarms[0].label == "Lupulo Amargor"


def test_hop_alarm_does_not_fire_twice_for_same_step_run(alarm_setup):
    runtime, recipe, state_path = alarm_setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.acknowledge_alarm(engine.pending_alarms[0].id)
    engine.skip_next(now=1001.0)
    for a in list(engine.pending_alarms):
        engine.acknowledge_alarm(a.id)
    engine.skip_next(now=1002.0)
    for a in list(engine.pending_alarms):
        engine.acknowledge_alarm(a.id)

    runtime.inject_sensor("boil_temp", 30.0)
    engine.tick(now=1002.0)
    engine.tick(now=1003.0)  # holding
    engine.tick(now=1038.0)  # dispara alarme de 90s
    assert len(engine.pending_alarms) == 1
    engine.acknowledge_alarm(engine.pending_alarms[0].id)

    engine.tick(now=1039.0)  # ainda nao bateu o segundo (0s) -- nao deve re-disparar o primeiro
    assert engine.pending_alarms == []


def test_hop_alarm_with_zero_minutes_remaining_fires_at_end_of_hold(alarm_setup):
    runtime, recipe, state_path = alarm_setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.acknowledge_alarm(engine.pending_alarms[0].id)
    engine.skip_next(now=1001.0)
    for a in list(engine.pending_alarms):
        engine.acknowledge_alarm(a.id)
    engine.skip_next(now=1002.0)
    for a in list(engine.pending_alarms):
        engine.acknowledge_alarm(a.id)

    runtime.inject_sensor("boil_temp", 30.0)
    engine.tick(now=1002.0)
    engine.tick(now=1003.0)  # holding, hold_started_at=1003
    engine.tick(now=1038.0)  # dispara o de 90s
    engine.acknowledge_alarm(engine.pending_alarms[0].id)

    engine.tick(now=1122.0)  # 119s decorridos, falta 1s -> ainda nao bateu 0s
    assert engine.pending_alarms == []

    engine.tick(now=1123.0)  # 120s -> hold completo, step avanca (finished) e dispara vessel_end + hop 0min
    # ordem: hop alarm checado antes do advance, entao "Whirlpool" dispara primeiro, depois "Final Fervura"
    alarms = engine.pending_alarms
    labels = [a.label for a in alarms]
    assert "Whirlpool" in labels
    assert "Final Fervura" in labels


def test_acknowledge_alarm_removes_from_pending(alarm_setup):
    runtime, recipe, state_path = alarm_setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    alarm_id = engine.pending_alarms[0].id

    engine.acknowledge_alarm(alarm_id)
    assert engine.pending_alarms == []


def test_acknowledge_unknown_alarm_id_is_noop(alarm_setup):
    runtime, recipe, state_path = alarm_setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.acknowledge_alarm(99999)  # nao deve lancar
    assert len(engine.pending_alarms) == 1  # alarme real continua la


def test_pending_alarms_persist_across_engine_restart(alarm_setup):
    runtime, recipe, state_path = alarm_setup
    engine1 = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine1.start(now=1000.0)
    assert len(engine1.pending_alarms) == 1

    engine2 = RecipeEngine(runtime, recipe, state_path, now=1001.0)
    # crash recovery aplica failsafe e muda status, mas o alarme pendente sobrevive
    assert len(engine2.pending_alarms) == 1
    assert engine2.pending_alarms[0].label == "Início Mostura"


def test_skip_previous_does_not_fire_alarms(alarm_setup):
    runtime, recipe, state_path = alarm_setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.acknowledge_alarm(engine.pending_alarms[0].id)
    engine.skip_next(now=1001.0)  # step0->1, mash->mash, sem alarme
    assert engine.pending_alarms == []

    engine.skip_previous(now=1002.0)  # volta pra step0 -- nao deve disparar alarme (acao manual)
    assert engine.pending_alarms == []


def test_reset_current_step_does_not_fire_alarms(alarm_setup):
    runtime, recipe, state_path = alarm_setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.acknowledge_alarm(engine.pending_alarms[0].id)

    engine.reset_current_step(now=1005.0)
    assert engine.pending_alarms == []
