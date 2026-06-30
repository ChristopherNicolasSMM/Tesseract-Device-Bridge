"""
ATENÇÃO: estes testes usam gpiozero.pins.mock (MockFactory + MockPWMPin)
— validam só a "fiação" (qual classe é instanciada, qual valor é
escrito/lido), nunca o comportamento elétrico real de um pino físico.
Não substituem teste manual em Raspberry Pi de verdade.
"""

import pytest
from gpiozero import Device
from gpiozero.pins.mock import MockFactory, MockPWMPin

from gpio.real_backend import RealGPIOBackend, register_analog_driver


@pytest.fixture(autouse=True)
def mock_pin_factory():
    original = Device.pin_factory
    Device.pin_factory = MockFactory(pin_class=MockPWMPin)
    yield
    Device.pin_factory.reset()
    Device.pin_factory = original


def test_setup_output_and_write_true():
    backend = RealGPIOBackend()
    backend.setup(pin=18, mode="output")
    backend.write(18, True)
    assert backend.read(18) == 1


def test_setup_output_and_write_false():
    backend = RealGPIOBackend()
    backend.setup(pin=18, mode="output")
    backend.write(18, False)
    assert backend.read(18) == 0


def test_setup_pwm_and_write_value_in_0_100_scale():
    backend = RealGPIOBackend()
    backend.setup(pin=19, mode="pwm", pwm_frequency=1000)
    backend.write(19, 50.0)
    assert backend.read(19) == pytest.approx(50.0)


def test_setup_pwm_clamps_out_of_range_values():
    backend = RealGPIOBackend()
    backend.setup(pin=19, mode="pwm")
    backend.write(19, 150.0)
    assert backend.read(19) == pytest.approx(100.0)

    backend.write(19, -10.0)
    assert backend.read(19) == pytest.approx(0.0)


def test_setup_input_reads_digital_value():
    backend = RealGPIOBackend()
    backend.setup(pin=20, mode="input")
    assert backend.read(20) == 0  # MockPin digital input default


def test_write_on_input_pin_raises_value_error():
    backend = RealGPIOBackend()
    backend.setup(pin=20, mode="input")
    with pytest.raises(ValueError):
        backend.write(20, True)


def test_invalid_mode_raises_value_error():
    backend = RealGPIOBackend()
    with pytest.raises(ValueError):
        backend.setup(pin=1, mode="invalid_mode")


def test_input_analog_without_registered_driver_raises_not_implemented():
    backend = RealGPIOBackend()
    with pytest.raises(NotImplementedError, match="Nenhum driver analógico"):
        backend.setup(pin=4, mode="input_analog", driver="totally_unknown_driver", address="x")


def test_input_analog_with_registered_driver():
    class FakeAnalogDevice:
        def __init__(self, pin, **kwargs):
            self.value = 42.0

    register_analog_driver("fake_driver", FakeAnalogDevice)
    backend = RealGPIOBackend()
    backend.setup(pin=4, mode="input_analog", driver="fake_driver")
    assert backend.read(4) == 42.0


def test_multiple_ds18b20_sensors_share_same_pin_distinguished_by_address(tmp_path):
    """
    Cenário real da interface CraftBeerPi (MAZZA): 3 sensores DS18B20 no
    mesmo GPIO4, cada um com endereço ROM próprio.
    """
    for address, milli_c in [("28-aaa", 25000), ("28-bbb", 67000), ("28-ccc", 18500)]:
        device_dir = tmp_path / address
        device_dir.mkdir()
        (device_dir / "w1_slave").write_text(
            f"4e 01 4b 46 7f ff 0e 10 68 : crc=68 YES\n4e 01 4b 46 7f ff 0e 10 68 t={milli_c}\n",
            encoding="ascii",
        )

    backend = RealGPIOBackend()
    backend.setup(pin=4, mode="input_analog", driver="ds18b20", address="28-aaa", base_path=str(tmp_path))
    backend.setup(pin=4, mode="input_analog", driver="ds18b20", address="28-bbb", base_path=str(tmp_path))
    backend.setup(pin=4, mode="input_analog", driver="ds18b20", address="28-ccc", base_path=str(tmp_path))

    assert backend.read(4, address="28-aaa") == 25.0
    assert backend.read(4, address="28-bbb") == 67.0
    assert backend.read(4, address="28-ccc") == 18.5


def test_read_unconfigured_pin_raises_key_error():
    backend = RealGPIOBackend()
    with pytest.raises(KeyError):
        backend.read(99)


def test_teardown_closes_device_and_removes_state():
    backend = RealGPIOBackend()
    backend.setup(pin=18, mode="output")
    backend.teardown(18)
    with pytest.raises(KeyError):
        backend.read(18)


def test_teardown_on_unconfigured_pin_is_noop():
    backend = RealGPIOBackend()
    backend.teardown(99)  # não deve lançar
