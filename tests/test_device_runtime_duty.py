"""
Testes do controle de potência (duty-cycle / time-proportioning) do
DeviceRuntime: prioridade entre failsafe, override manual e duty de
receita, e o ciclo de suspensão/retomada por resume_all_suspended_overrides().

Contexto de arquitetura (skill de decisão registrada na conversa):
DeviceRuntime é o dono único do TimeProportioningController de cada
atuador com hardware.window_seconds — nem receita nem painel escrevem
direto no GPIO desses atuadores, só pedem um duty. Prioridade a cada
tick_duty(): failsafe suspenso > override manual > duty da receita >
repouso (0%).
"""

import textwrap

import pytest

from config import BridgeConfig
from device_runtime import DeviceRuntime, DeviceRuntimeError
from gpio.simulated_backend import SimulatedGPIOBackend


def make_config(tmp_path, content: str) -> BridgeConfig:
    path = tmp_path / "devices.yml"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return BridgeConfig.load(path)


YAML_WITH_DUTY = """
mqtt:
  enabled: false
backend: simulated
panel:
  enabled: true

devices:
  - id: mash_heater
    name: "Resistencia Mostura"
    role: actuator
    subtype: digital
    command_topic: "actuators/mash_heater/set"
    hardware:
      pin: 17
      window_seconds: 10
    failsafe_value: false
    is_risk: true
    failsafe_timeout_seconds: 30

  - id: mash_pump
    name: "Bomba Mostura"
    role: actuator
    subtype: digital
    command_topic: "actuators/mash_pump/set"
    hardware:
      pin: 20
    failsafe_value: false
    is_risk: true
    failsafe_timeout_seconds: 30
"""


@pytest.fixture
def runtime(tmp_path):
    config = make_config(tmp_path, YAML_WITH_DUTY)
    backend = SimulatedGPIOBackend()
    return DeviceRuntime(config, backend)


# ---- has_duty_control / DeviceState -----------------------------------


def test_has_duty_control_true_for_device_with_window_seconds(runtime):
    assert runtime.has_duty_control("mash_heater") is True


def test_has_duty_control_false_for_device_without_window_seconds(runtime):
    assert runtime.has_duty_control("mash_pump") is False


def test_device_state_exposes_duty_fields_for_duty_device(runtime):
    state = runtime.get_state("mash_heater")
    assert state.window_seconds == 10
    assert state.duty_percent == 0.0
    assert state.duty_source == "idle"


def test_device_state_duty_fields_none_for_non_duty_device(runtime):
    state = runtime.get_state("mash_pump")
    assert state.window_seconds is None
    assert state.duty_percent is None
    assert state.duty_source is None


# ---- set_manual_duty: validação -----------------------------------------


def test_set_manual_duty_on_non_duty_device_raises(runtime):
    with pytest.raises(DeviceRuntimeError):
        runtime.set_manual_duty("mash_pump", 50.0)


def test_set_manual_duty_out_of_range_raises(runtime):
    with pytest.raises(DeviceRuntimeError):
        runtime.set_manual_duty("mash_heater", 150.0)
    with pytest.raises(DeviceRuntimeError):
        runtime.set_manual_duty("mash_heater", -1.0)


def test_set_manual_duty_non_numeric_raises(runtime):
    with pytest.raises(DeviceRuntimeError):
        runtime.set_manual_duty("mash_heater", "quarenta")


def test_get_duty_state_on_non_duty_device_raises(runtime):
    with pytest.raises(DeviceRuntimeError):
        runtime.get_duty_state("mash_pump")


def test_set_pid_duty_on_non_duty_device_raises(runtime):
    with pytest.raises(DeviceRuntimeError):
        runtime.set_pid_duty("mash_pump", 50.0)


# ---- prioridade: manual > pid --------------------------------------------


def test_pid_duty_applied_when_no_manual_override(runtime):
    runtime.set_pid_duty("mash_heater", 40.0)
    duty = runtime.get_duty_state("mash_heater")
    assert duty.duty_percent == 40.0
    assert duty.source == "pid"


def test_manual_override_wins_over_pid_duty(runtime):
    runtime.set_pid_duty("mash_heater", 40.0)
    runtime.set_manual_duty("mash_heater", 90.0)

    duty = runtime.get_duty_state("mash_heater")
    assert duty.duty_percent == 90.0
    assert duty.source == "manual"


def test_clearing_manual_override_falls_back_to_pid_duty(runtime):
    runtime.set_pid_duty("mash_heater", 40.0)
    runtime.set_manual_duty("mash_heater", 90.0)
    runtime.set_manual_duty("mash_heater", None)  # limpa

    duty = runtime.get_duty_state("mash_heater")
    assert duty.duty_percent == 40.0
    assert duty.source == "pid"


def test_no_manual_no_pid_is_idle_zero(runtime):
    duty = runtime.get_duty_state("mash_heater")
    assert duty.duty_percent == 0.0
    assert duty.source == "idle"


# ---- tick_duty escreve no GPIO conforme o TPC ----------------------------


def test_tick_duty_turns_actuator_on_within_duty_window(runtime):
    runtime.set_manual_duty("mash_heater", 100.0)
    runtime.tick_duty(now=0.0)
    assert runtime.get_state("mash_heater").value is True


def test_tick_duty_keeps_actuator_off_when_duty_zero(runtime):
    runtime.set_pid_duty("mash_heater", 0.0)
    runtime.tick_duty(now=0.0)
    assert runtime.get_state("mash_heater").value is False


def test_tick_duty_respects_window_boundaries(runtime):
    # window_seconds=10, duty=50% -> ligado nos primeiros 5s, desligado depois
    runtime.set_manual_duty("mash_heater", 50.0)
    runtime.tick_duty(now=100.0)  # abre a janela em now=100
    assert runtime.get_state("mash_heater").value is True

    runtime.tick_duty(now=104.0)  # ainda dentro dos 5s "ligado"
    assert runtime.get_state("mash_heater").value is True

    runtime.tick_duty(now=106.0)  # passou dos 5s -> desligado até nova janela
    assert runtime.get_state("mash_heater").value is False


def test_pid_duty_drop_mid_window_does_not_cut_current_window_short(runtime):
    """
    Regressão do bug relatado: o PID reduzindo o duty no meio de uma
    janela em andamento (comportamento normal perto do alvo) não pode
    encolher retroativamente o "tempo ligado" já decidido para essa
    janela — só a próxima janela deve refletir o novo valor. O source
    continua "pid" o tempo todo, então isso passa pelo caminho
    travado por janela (set_duty_cycle), não pelo force_lock.
    """
    runtime.set_pid_duty("mash_heater", 100.0)
    runtime.tick_duty(now=0.0)  # janela abre (window_seconds=10), locked=100%
    assert runtime.get_state("mash_heater").value is True

    # PID cai pra 0% no meio da janela — mesmo source ("pid"), não
    # deve desligar antes do fim da janela travada.
    runtime.set_pid_duty("mash_heater", 0.0)
    runtime.tick_duty(now=5.0)
    assert runtime.get_state("mash_heater").value is True

    runtime.tick_duty(now=9.0)
    assert runtime.get_state("mash_heater").value is True

    # só na próxima janela o duty=0% pendente entra em vigor.
    runtime.tick_duty(now=10.0)
    assert runtime.get_state("mash_heater").value is False


# ---- failsafe: suspende duty, sempre vence --------------------------------


def test_apply_failsafe_suspends_manual_override(runtime):
    runtime.set_manual_duty("mash_heater", 80.0)
    runtime.tick_duty(now=0.0)
    assert runtime.get_state("mash_heater").value is True

    runtime.apply_failsafe("mash_heater")
    assert runtime.get_state("mash_heater").value is False  # escrita imediata

    # Mesmo com o override manual ainda "guardado" (80%), o próximo
    # tick_duty NÃO pode religar — failsafe suspenso vence.
    runtime.tick_duty(now=1.0)
    assert runtime.get_state("mash_heater").value is False
    duty = runtime.get_duty_state("mash_heater")
    assert duty.source == "failsafe_suspended"
    assert duty.duty_percent == 0.0


def test_apply_failsafe_suspends_pid_duty_too(runtime):
    runtime.set_pid_duty("mash_heater", 100.0)
    runtime.apply_failsafe("mash_heater")
    runtime.tick_duty(now=1.0)
    assert runtime.get_state("mash_heater").value is False


def test_apply_failsafe_external_also_suspends(runtime):
    runtime.set_manual_duty("mash_heater", 80.0)
    runtime.apply_failsafe_external("mash_heater", False)
    runtime.tick_duty(now=1.0)
    assert runtime.get_state("mash_heater").value is False
    assert runtime.get_duty_state("mash_heater").source == "failsafe_suspended"


def test_apply_failsafe_on_device_without_duty_control_still_works(runtime):
    # Regressão: apply_failsafe continua funcionando normalmente pra
    # atuadores sem controle de potência (comportamento anterior).
    runtime.set_actuator("mash_pump", True)
    state = runtime.apply_failsafe("mash_pump")
    assert state.value is False


def test_resume_all_suspended_overrides_restores_manual_duty(runtime):
    runtime.set_manual_duty("mash_heater", 80.0)
    runtime.apply_failsafe("mash_heater")
    runtime.tick_duty(now=1.0)
    assert runtime.get_state("mash_heater").value is False

    runtime.resume_all_suspended_overrides()
    runtime.tick_duty(now=1.0)
    assert runtime.get_state("mash_heater").value is True  # override de 80% voltou sozinho

    duty = runtime.get_duty_state("mash_heater")
    assert duty.source == "manual"
    assert duty.duty_percent == 80.0


def test_resume_without_prior_failsafe_is_a_safe_noop(runtime):
    runtime.set_manual_duty("mash_heater", 50.0)
    runtime.resume_all_suspended_overrides()  # nada suspenso -- não deve quebrar nada
    duty = runtime.get_duty_state("mash_heater")
    assert duty.source == "manual"
    assert duty.duty_percent == 50.0


# ---- set_manual_duty_percent / set_manual_enabled (interruptor separado
# do valor) -- ajustar o % sozinho nunca arma o atuador ----------------------


def test_set_manual_duty_percent_alone_does_not_enable(runtime):
    runtime.set_manual_duty_percent("mash_heater", 60.0)
    duty = runtime.get_duty_state("mash_heater")
    assert duty.duty_percent == 0.0
    assert duty.source == "idle"

    state = runtime.get_state("mash_heater")
    assert state.manual_duty_percent == 60.0  # valor guardado
    assert state.duty_enabled is False  # mas não armado


def test_set_manual_enabled_true_applies_configured_percent(runtime):
    runtime.set_manual_duty_percent("mash_heater", 60.0)
    runtime.set_manual_enabled("mash_heater", True)

    duty = runtime.get_duty_state("mash_heater")
    assert duty.duty_percent == 60.0
    assert duty.source == "manual"


def test_set_manual_enabled_true_without_percent_defaults_to_zero(runtime):
    runtime.set_manual_enabled("mash_heater", True)
    duty = runtime.get_duty_state("mash_heater")
    assert duty.duty_percent == 0.0
    assert duty.source == "manual"  # armado, só que em 0%


def test_disabling_keeps_configured_percent_for_next_time(runtime):
    runtime.set_manual_duty_percent("mash_heater", 70.0)
    runtime.set_manual_enabled("mash_heater", True)
    runtime.set_manual_enabled("mash_heater", False)

    state = runtime.get_state("mash_heater")
    assert state.manual_duty_percent == 70.0  # preservado
    assert state.duty_enabled is False
    assert state.duty_percent == 0.0
    assert state.duty_source == "idle"

    runtime.set_manual_enabled("mash_heater", True)  # religa sem reconfigurar
    duty = runtime.get_duty_state("mash_heater")
    assert duty.duty_percent == 70.0


def test_changing_percent_while_enabled_takes_effect_immediately(runtime):
    runtime.set_manual_enabled("mash_heater", True)
    runtime.set_manual_duty_percent("mash_heater", 25.0)

    duty = runtime.get_duty_state("mash_heater")
    assert duty.duty_percent == 25.0
    assert duty.source == "manual"


def test_set_manual_duty_percent_on_non_duty_device_raises(runtime):
    with pytest.raises(DeviceRuntimeError):
        runtime.set_manual_duty_percent("mash_pump", 50.0)


def test_set_manual_enabled_on_non_duty_device_raises(runtime):
    with pytest.raises(DeviceRuntimeError):
        runtime.set_manual_enabled("mash_pump", True)


def test_tick_duty_does_not_energize_when_percent_set_but_not_enabled(runtime):
    runtime.set_manual_duty_percent("mash_heater", 100.0)
    runtime.tick_duty(now=0.0)
    assert runtime.get_state("mash_heater").value is False


def test_failsafe_suspends_regardless_of_enabled_state(runtime):
    runtime.set_manual_duty_percent("mash_heater", 80.0)
    runtime.set_manual_enabled("mash_heater", True)
    runtime.tick_duty(now=0.0)
    assert runtime.get_state("mash_heater").value is True

    runtime.apply_failsafe("mash_heater")
    runtime.tick_duty(now=1.0)
    assert runtime.get_state("mash_heater").value is False

    runtime.resume_all_suspended_overrides()
    runtime.tick_duty(now=1.0)
    assert runtime.get_state("mash_heater").value is True  # duty_enabled sobreviveu ao failsafe
