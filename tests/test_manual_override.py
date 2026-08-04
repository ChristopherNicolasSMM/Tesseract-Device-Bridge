"""
Testes do override manual genérico (DeviceRuntime.set_manual_override /
has_manual_override) — mecanismo separado do controle de potência
(duty-cycle), usado por atuadores simples liga/desliga que o
RecipeEngine também gerencia automaticamente (bombas).

Contexto do bug que este mecanismo evita: RecipeEngine._apply_pumps()
decide liga/desliga comparando a lista de pumps da etapa atual contra
seu PRÓPRIO bookkeeping interno (self._active_pumps) — nunca contra o
estado físico real. Sem um jeito de marcar "isto está sob controle
manual", um comando manual aplicado enquanto a receita está rodando
pode ficar "escondido" do RecipeEngine (que não sabe que a realidade
mudou) e ser desfeito silenciosamente na próxima troca de etapa, quando
o diff resultar numa reescrita que reverte o valor manual.
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


YAML_BASIC = """
mqtt:
  enabled: false
backend: simulated
panel:
  enabled: true

devices:
  - id: mash_tun_temp
    name: "Temperatura Mostura"
    role: sensor
    subtype: temperature
    state_topic: "sensors/mash_tun_temp/state"
    hardware:
      pin: 4
    simulated:
      initial_value: 25.0

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
    config = make_config(tmp_path, YAML_BASIC)
    backend = SimulatedGPIOBackend()
    return DeviceRuntime(config, backend)


# ---- DeviceRuntime.set_manual_override / has_manual_override -------------


def test_has_manual_override_false_by_default(runtime):
    assert runtime.has_manual_override("mash_pump") is False


def test_set_manual_override_writes_and_registers(runtime):
    state = runtime.set_manual_override("mash_pump", True)
    assert state.value is True
    assert state.manual_override is True
    assert runtime.has_manual_override("mash_pump") is True


def test_set_manual_override_false_is_registered_not_confused_with_unset(runtime):
    """
    False é um valor válido de override -- has_manual_override precisa
    diferenciar "nunca definido" (None) de "definido como False".
    """
    runtime.set_manual_override("mash_pump", False)
    assert runtime.has_manual_override("mash_pump") is True
    assert runtime.get_state("mash_pump").manual_override is False


def test_clearing_manual_override_with_none(runtime):
    runtime.set_manual_override("mash_pump", True)
    runtime.set_manual_override("mash_pump", None)
    assert runtime.has_manual_override("mash_pump") is False
    assert runtime.get_state("mash_pump").manual_override is None


def test_set_manual_override_on_sensor_raises(runtime):
    with pytest.raises(DeviceRuntimeError):
        runtime.set_manual_override("mash_tun_temp", True)


def test_manual_override_none_for_untouched_actuator_state(runtime):
    state = runtime.get_state("mash_pump")
    assert state.manual_override is None


# ---- failsafe suspende e resume_all_suspended_overrides reaplica ---------


def test_apply_failsafe_suspends_manual_override(runtime):
    runtime.set_manual_override("mash_pump", True)
    assert runtime.get_state("mash_pump").value is True

    runtime.apply_failsafe("mash_pump")
    assert runtime.get_state("mash_pump").value is False  # escrita imediata do failsafe


def test_set_manual_override_while_suspended_does_not_write_physically(runtime):
    runtime.set_manual_override("mash_pump", True)
    runtime.apply_failsafe("mash_pump")

    # Tenta religar manualmente enquanto ainda suspenso -- não deve
    # escrever fisicamente (failsafe sempre vence).
    state = runtime.set_manual_override("mash_pump", True)
    assert runtime.get_state("mash_pump").value is False


def test_resume_reapplies_suspended_manual_override(runtime):
    runtime.set_manual_override("mash_pump", True)
    runtime.apply_failsafe("mash_pump")
    assert runtime.get_state("mash_pump").value is False

    runtime.resume_all_suspended_overrides()
    assert runtime.get_state("mash_pump").value is True  # override de volta, reescrito de fato


def test_apply_failsafe_external_also_suspends_manual_override(runtime):
    runtime.set_manual_override("mash_pump", True)
    runtime.apply_failsafe_external("mash_pump", False)
    assert runtime.get_state("mash_pump").value is False

    runtime.resume_all_suspended_overrides()
    assert runtime.get_state("mash_pump").value is True
