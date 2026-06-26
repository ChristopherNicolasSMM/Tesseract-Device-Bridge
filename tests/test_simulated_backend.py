import logging

import pytest

from gpio.simulated_backend import SimulatedGPIOBackend


def test_setup_output_with_default_initial_value():
    backend = SimulatedGPIOBackend()
    backend.setup(pin=18, mode="output")
    assert backend.read(18) is False


def test_setup_pwm_default_initial_value_is_zero():
    backend = SimulatedGPIOBackend()
    backend.setup(pin=18, mode="pwm", pwm_frequency=1000)
    assert backend.read(18) == 0.0


def test_setup_with_explicit_initial_value():
    backend = SimulatedGPIOBackend()
    backend.setup(pin=4, mode="input_analog", initial_value=25.0, min=0, max=120)
    assert backend.read(4) == 25.0


def test_setup_invalid_mode_raises():
    backend = SimulatedGPIOBackend()
    with pytest.raises(ValueError):
        backend.setup(pin=1, mode="invalid_mode")


def test_write_on_output_pin_updates_value():
    backend = SimulatedGPIOBackend()
    backend.setup(pin=20, mode="output")
    backend.write(20, True)
    assert backend.read(20) is True


def test_write_on_pwm_pin_updates_value():
    backend = SimulatedGPIOBackend()
    backend.setup(pin=18, mode="pwm")
    backend.write(18, 75.0)
    assert backend.read(18) == 75.0


def test_write_on_input_pin_raises_value_error():
    """
    Regra central do bridge: write() nunca pode ser usado para "fingir"
    uma leitura de sensor — isso teria que ser inject(). Se isso não
    fosse bloqueado, um bug em bridge.py poderia silenciosamente
    sobrescrever uma leitura real sem ninguém notar.
    """
    backend = SimulatedGPIOBackend()
    backend.setup(pin=4, mode="input")
    with pytest.raises(ValueError):
        backend.write(4, True)


def test_inject_on_input_pin_updates_value():
    backend = SimulatedGPIOBackend()
    backend.setup(pin=4, mode="input_analog", initial_value=25.0)
    backend.inject(4, 99.5)
    assert backend.read(4) == 99.5


def test_inject_on_output_pin_raises_value_error():
    """
    Inverso do teste anterior: inject() é exclusivo de pinos de entrada.
    Um atuador simulado só muda de estado via write() (comando real ou
    vindo do painel chamando write() em nome do usuário).
    """
    backend = SimulatedGPIOBackend()
    backend.setup(pin=20, mode="output")
    with pytest.raises(ValueError):
        backend.inject(20, True)


def test_read_on_unconfigured_pin_raises_key_error():
    backend = SimulatedGPIOBackend()
    with pytest.raises(KeyError):
        backend.read(99)


def test_write_on_unconfigured_pin_raises_key_error():
    backend = SimulatedGPIOBackend()
    with pytest.raises(KeyError):
        backend.write(99, True)


def test_teardown_removes_pin():
    backend = SimulatedGPIOBackend()
    backend.setup(pin=20, mode="output")
    backend.teardown(20)
    with pytest.raises(KeyError):
        backend.read(20)


def test_teardown_on_unconfigured_pin_is_noop():
    """Teardown não deve levantar erro se o pino nunca existiu."""
    backend = SimulatedGPIOBackend()
    backend.teardown(99)  # não deve lançar


def test_snapshot_reflects_current_state_of_all_pins():
    backend = SimulatedGPIOBackend()
    backend.setup(pin=4, mode="input_analog", initial_value=25.0, min=0, max=120)
    backend.setup(pin=18, mode="pwm", pwm_frequency=1000)
    backend.write(18, 50.0)

    snapshot = backend.snapshot()

    assert snapshot[4]["mode"] == "input_analog"
    assert snapshot[4]["value"] == 25.0
    assert snapshot[4]["config"] == {"min": 0, "max": 120}
    assert snapshot[18]["mode"] == "pwm"
    assert snapshot[18]["value"] == 50.0


def test_snapshot_is_a_copy_not_a_live_reference():
    """
    Mutar o dict retornado por snapshot() nunca pode afetar o estado
    interno do backend — isso protegeria, por exemplo, o painel web de
    corromper o estado real ao manipular o que recebeu para exibição.
    """
    backend = SimulatedGPIOBackend()
    backend.setup(pin=20, mode="output")

    snapshot = backend.snapshot()
    snapshot[20]["value"] = True
    snapshot[20]["config"]["hacked"] = True

    assert backend.read(20) is False
    assert "hacked" not in backend.snapshot()[20]["config"]


def test_setup_logs_at_info_level(caplog):
    backend = SimulatedGPIOBackend()
    with caplog.at_level(logging.INFO, logger="tesseract_bridge.gpio.simulated"):
        backend.setup(pin=4, mode="input_analog", initial_value=25.0)
    assert any("setup" in record.message for record in caplog.records)


def test_write_logs_at_info_level(caplog):
    backend = SimulatedGPIOBackend()
    backend.setup(pin=18, mode="pwm")
    with caplog.at_level(logging.INFO, logger="tesseract_bridge.gpio.simulated"):
        backend.write(18, 80.0)
    assert any("write" in record.message for record in caplog.records)


def test_inject_logs_at_info_level(caplog):
    backend = SimulatedGPIOBackend()
    backend.setup(pin=4, mode="input_analog", initial_value=25.0)
    with caplog.at_level(logging.INFO, logger="tesseract_bridge.gpio.simulated"):
        backend.inject(4, 30.0)
    assert any("inject" in record.message for record in caplog.records)


def test_multiple_pins_are_independent():
    backend = SimulatedGPIOBackend()
    backend.setup(pin=4, mode="input_analog", initial_value=25.0)
    backend.setup(pin=20, mode="output")

    backend.inject(4, 40.0)
    backend.write(20, True)

    assert backend.read(4) == 40.0
    assert backend.read(20) is True
