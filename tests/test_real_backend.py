"""
Testes de wiring do RealGPIOBackend.

ATENÇÃO: estes testes usam gpiozero.pins.mock (MockFactory + MockPWMPin)
— validam só a "fiação" (qual classe é instanciada, qual modo é
configurado, qual valor é escrito/lido, se active_high está correto),
NUNCA o comportamento elétrico real de um pino físico. Não substituem
teste manual em Raspberry Pi de verdade usando tools/gpio_test.py.

A mudança da sessão de diagnóstico de GPIO (2026-07):
  - O pin_factory agora é passado explicitamente ao RealGPIOBackend()
    em vez de ser definido no global Device.pin_factory. Isso garante
    que todos os devices criados dentro de uma instância do backend
    usam o mesmo factory — comportamento mais robusto em produção e
    mais previsível nos testes.
  - Adicionado campo active_high (bool, default True) propagado do
    devices.yml até o DigitalOutputDevice/PWMOutputDevice.
  - _pick_pin_factory() tenta lgpio → RPi.GPIO → pigpio → None.
"""

import pytest
from gpiozero.pins.mock import MockFactory, MockPWMPin

from gpio.real_backend import RealGPIOBackend, register_analog_driver


@pytest.fixture
def factory():
    """
    MockFactory com suporte a PWM (MockPWMPin) — necessário para que
    o gpiozero não rejeite PWMOutputDevice em ambiente sem hardware real.
    """
    return MockFactory(pin_class=MockPWMPin)


@pytest.fixture
def backend(factory):
    """Backend instanciado com MockFactory para todos os testes de wiring."""
    return RealGPIOBackend(pin_factory=factory)


# ---- saída digital ---------------------------------------------------------

def test_setup_output_and_write_true(backend):
    backend.setup(pin=18, mode="output")
    backend.write(18, True)
    assert backend.read(18) == 1


def test_setup_output_and_write_false(backend):
    backend.setup(pin=18, mode="output")
    backend.write(18, True)
    backend.write(18, False)
    assert backend.read(18) == 0


def test_active_high_true_default(backend, factory):
    """
    active_high=True (default): write(True) deve colocar o pino em HIGH.
    No mock do gpiozero, state=1.0 significa pino em HIGH (float 0.0–1.0).
    """
    backend.setup(pin=18, mode="output")  # active_high omitido → default True
    backend.write(18, True)
    pin_obj = factory.pin(18)
    # Estado 1.0 = HIGH no mock
    assert pin_obj.state == pytest.approx(1.0)


def test_active_high_false_inverted(backend, factory):
    """
    active_high=False: write(True) deve colocar o pino em LOW.
    Relé active-low: LOW no GPIO fecha o relé.
    No mock, state=0.0 significa pino em LOW.
    """
    backend.setup(pin=18, mode="output", active_high=False)
    backend.write(18, True)   # "ligar" logicamente
    pin_obj = factory.pin(18)
    # Com active_high=False, ligar = colocar em LOW → state 0.0
    assert pin_obj.state == pytest.approx(0.0)


def test_active_high_propagated_to_pwm(backend, factory):
    """active_high deve ser aceito também em mode='pwm' sem erros."""
    backend.setup(pin=18, mode="pwm", active_high=True)
    backend.write(18, 50)
    # PWM: 50 (escala bridge) → 0.5 (escala gpiozero)
    assert pytest.approx(backend.read(18), abs=0.1) == 50.0


# ---- PWM -------------------------------------------------------------------

def test_setup_pwm_and_write_value_in_0_100_scale(backend):
    backend.setup(pin=18, mode="pwm")
    backend.write(18, 75)
    # write em escala 0-100; read também retorna 0-100
    assert pytest.approx(backend.read(18), abs=0.1) == 75.0


def test_setup_pwm_clamps_out_of_range_values(backend):
    backend.setup(pin=18, mode="pwm")
    backend.write(18, 150)   # acima de 100 → clampado para 100
    assert pytest.approx(backend.read(18), abs=0.1) == 100.0

    backend.write(18, -10)   # abaixo de 0 → clampado para 0
    assert pytest.approx(backend.read(18), abs=0.1) == 0.0


# ---- entrada digital -------------------------------------------------------

def test_setup_input_reads_digital_value(backend, factory):
    backend.setup(pin=18, mode="input")
    # No mock, o valor inicial de um input é False (LOW)
    assert backend.read(18) == False


# ---- erros esperados -------------------------------------------------------

def test_write_on_input_pin_raises_value_error(backend):
    backend.setup(pin=18, mode="input")
    with pytest.raises(ValueError, match="write\\(\\) chamado"):
        backend.write(18, True)


def test_invalid_mode_raises_value_error(backend):
    with pytest.raises(ValueError, match="Modo inválido"):
        backend.setup(pin=18, mode="modo_inexistente")


def test_input_analog_without_registered_driver_raises_not_implemented(backend):
    with pytest.raises(NotImplementedError, match="Nenhum driver analógico"):
        backend.setup(pin=18, mode="input_analog", driver="sensor_inexistente")


# ---- driver analógico customizado -----------------------------------------

def test_input_analog_with_registered_driver(backend, tmp_path):
    """
    Verifica que register_analog_driver() funciona: o driver é chamado
    com o pin e os kwargs do devices.yml, e read() retorna o valor do driver.
    """
    class FakeSensor:
        def __init__(self, pin, **kwargs):
            self.pin = pin

        @property
        def value(self):
            return 42.0

    register_analog_driver("fake_sensor", FakeSensor)
    backend.setup(pin=4, mode="input_analog", driver="fake_sensor")
    assert backend.read(4) == 42.0


# ---- múltiplos sensores DS18B20 no mesmo pino ------------------------------

def test_multiple_ds18b20_sensors_share_same_pin_distinguished_by_address(tmp_path):
    """
    Três sensores DS18B20 no mesmo pino (barramento 1-Wire da MAZZA):
    cada um tem seu próprio Ds18b20Reader identificado pelo address.
    setup() e read() com address diferente acessam devices diferentes.

    Usa o base_path injetável do Ds18b20Reader para criar arquivos
    w1_slave falsos no tmp_path — sem precisar de patch de método privado.
    """
    readings = {
        "28-aaa": 67000,    # 67.000 °C em milésimos (formato real do kernel)
        "28-bbb": 25500,
        "28-ccc": 100000,
    }

    # Cria a estrutura de arquivos que o driver espera:
    # <base_path>/<address>/w1_slave
    for address, temp_milli in readings.items():
        sensor_dir = tmp_path / address
        sensor_dir.mkdir()
        w1_slave = sensor_dir / "w1_slave"
        # Formato real do arquivo w1_slave do kernel Linux:
        w1_slave.write_text(
            f"50 01 4b 46 7f ff 0c 10 1c : crc=1c YES\n"
            f"50 01 4b 46 7f ff 0c 10 1c t={temp_milli}\n"
        )

    backend = RealGPIOBackend(pin_factory=MockFactory(pin_class=MockPWMPin))

    for addr in readings:
        backend.setup(
            pin=4, mode="input_analog", driver="ds18b20",
            address=addr, base_path=str(tmp_path),
        )

    for addr, temp_milli in readings.items():
        valor = backend.read(4, address=addr)
        assert valor == pytest.approx(temp_milli / 1000.0, abs=0.01)


# ---- pino não configurado --------------------------------------------------

def test_read_unconfigured_pin_raises_key_error(backend):
    with pytest.raises(KeyError, match="não foi configurado"):
        backend.read(99)


# ---- teardown --------------------------------------------------------------

def test_teardown_closes_device_and_removes_state(backend):
    backend.setup(pin=18, mode="output")
    backend.write(18, True)
    backend.teardown(18)
    # Após teardown, read deve levantar KeyError
    with pytest.raises(KeyError):
        backend.read(18)


def test_teardown_on_unconfigured_pin_is_noop(backend):
    """teardown em pino nunca configurado não deve levantar exceção."""
    backend.teardown(99)  # não deve explodir


# ---- seleção de backend (sem hardware real) --------------------------------

def test_real_backend_accepts_explicit_pin_factory():
    """
    RealGPIOBackend aceita pin_factory explícito no construtor.
    Isso é o mecanismo usado pelos testes para injetar MockFactory
    em vez de tentar acessar /dev/gpiomem ou /dev/gpiochip0.
    """
    factory = MockFactory(pin_class=MockPWMPin)
    backend = RealGPIOBackend(pin_factory=factory)
    assert backend._pin_factory is factory


def test_real_backend_without_factory_does_not_crash_import():
    """
    _pick_pin_factory() retorna None graciosamente quando nenhum backend
    está disponível (ex.: rodando fora de um Pi), sem levantar exceção
    no import/construção. A falha real só ocorre em setup() quando o
    gpiozero tenta acessar hardware.
    """
    from gpio.real_backend import _pick_pin_factory
    # No sandbox (sem Pi), todos os backends vão falhar e retornar None
    # ou o gpiozero pode ter um mock disponível — o importante é que
    # não levanta exceção aqui.
    try:
        result = _pick_pin_factory()
        # Pode ser None ou um factory válido — ambos são aceitos
        assert result is None or hasattr(result, "pin")
    except Exception as e:
        pytest.fail(f"_pick_pin_factory() não deveria levantar exceção: {e}")
