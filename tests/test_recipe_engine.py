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
    hardware: { pin: 17 }
    failsafe_value: false
    is_risk: true
    failsafe_timeout_seconds: 30

  - id: boil_heater
    name: "Aquecedor Fervura"
    role: actuator
    subtype: digital
    command_topic: "actuators/boil_heater/set"
    hardware: { pin: 27 }
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
  mash:
    heater_device_id: mash_heater
    sensor_device_id: mash_tun_temp
    pid: { kp: 50.0, ki: 0.0, kd: 0.0 }
    window_seconds: 10
  boil:
    heater_device_id: boil_heater
    sensor_device_id: boil_temp
    pid: { kp: 50.0, ki: 0.0, kd: 0.0 }
    window_seconds: 10
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


def test_tick_activates_step_pumps(setup):
    runtime, recipe, state_path = setup
    engine = RecipeEngine(runtime, recipe, state_path, now=1000.0)
    engine.start(now=1000.0)
    engine.tick(now=1000.0)
    engine.tick(now=1001.0)
    assert runtime.get_state("pump_b1").value is True


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
