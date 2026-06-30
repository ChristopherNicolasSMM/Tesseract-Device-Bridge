import pytest

from recipe_engine.pid import PidController, PidGains


def test_proportional_only_output():
    pid = PidController(PidGains(kp=2.0, ki=0.0, kd=0.0))
    output = pid.compute(setpoint=70.0, current_value=60.0, dt=1.0)
    assert output == pytest.approx(20.0)  # erro=10, kp=2 -> 20


def test_output_clamped_to_max():
    pid = PidController(PidGains(kp=100.0, ki=0.0, kd=0.0))
    output = pid.compute(setpoint=70.0, current_value=0.0, dt=1.0)
    assert output == 100.0


def test_output_clamped_to_min():
    pid = PidController(PidGains(kp=100.0, ki=0.0, kd=0.0), output_min=0.0, output_max=100.0)
    output = pid.compute(setpoint=0.0, current_value=70.0, dt=1.0)
    assert output == 0.0


def test_integral_accumulates_over_multiple_calls():
    pid = PidController(PidGains(kp=0.0, ki=1.0, kd=0.0))
    out1 = pid.compute(setpoint=10.0, current_value=9.0, dt=1.0)  # erro=1, integral=1 -> out=1
    out2 = pid.compute(setpoint=10.0, current_value=9.0, dt=1.0)  # integral=2 -> out=2
    assert out1 == pytest.approx(1.0)
    assert out2 == pytest.approx(2.0)


def test_derivative_responds_to_error_change():
    pid = PidController(PidGains(kp=0.0, ki=0.0, kd=1.0), output_min=-100.0, output_max=100.0)
    pid.compute(setpoint=10.0, current_value=5.0, dt=1.0)  # erro=5, primeira chamada -> derivative=0
    output = pid.compute(setpoint=10.0, current_value=8.0, dt=1.0)  # erro=2, delta=-3 -> derivative=-3
    assert output == pytest.approx(-3.0)


def test_reset_clears_integral_and_previous_error():
    pid = PidController(PidGains(kp=0.0, ki=1.0, kd=1.0))
    pid.compute(setpoint=10.0, current_value=5.0, dt=1.0)
    pid.reset()
    # depois do reset, integral=0 e previous_error=None -> derivative=0 na próxima chamada
    output = pid.compute(setpoint=10.0, current_value=9.0, dt=1.0)  # erro=1, integral=0+1=1*ki=1, derivative=0
    assert output == pytest.approx(1.0)


def test_anti_windup_does_not_accumulate_integral_while_saturated():
    """
    Enquanto a saída está saturada no máximo, o integral não deve
    continuar acumulando (anti-windup por clamping) — senão, quando o
    erro finalmente cair, o sistema demoraria demais pra "desinflar" o
    integral acumulado (overshoot clássico de PID sem anti-windup).
    """
    pid = PidController(PidGains(kp=0.0, ki=50.0, kd=0.0), output_min=0.0, output_max=100.0)
    # Erro grande o bastante pra saturar logo na primeira chamada.
    pid.compute(setpoint=100.0, current_value=0.0, dt=1.0)
    pid.compute(setpoint=100.0, current_value=0.0, dt=1.0)
    pid.compute(setpoint=100.0, current_value=0.0, dt=1.0)
    # Integral não deveria ter acumulado nada além do necessário pra saturar.
    assert pid._integral <= 100.0 / 50.0 + 1e-9  # no máximo o suficiente pra atingir o limite


def test_dt_zero_or_negative_raises_value_error():
    pid = PidController(PidGains(kp=1.0, ki=0.0, kd=0.0))
    with pytest.raises(ValueError):
        pid.compute(setpoint=10.0, current_value=5.0, dt=0.0)
    with pytest.raises(ValueError):
        pid.compute(setpoint=10.0, current_value=5.0, dt=-1.0)


def test_invalid_output_range_raises_value_error():
    with pytest.raises(ValueError):
        PidController(PidGains(kp=1.0, ki=0.0, kd=0.0), output_min=100.0, output_max=0.0)


def test_zero_error_produces_zero_output_with_no_prior_state():
    pid = PidController(PidGains(kp=1.0, ki=1.0, kd=1.0))
    output = pid.compute(setpoint=70.0, current_value=70.0, dt=1.0)
    assert output == pytest.approx(0.0)


def test_realistic_approach_to_setpoint_over_multiple_steps():
    """
    Smoke test de comportamento: com ganhos razoáveis, a saída deve
    diminuir conforme a temperatura medida se aproxima do setpoint
    (convergência qualitativa, não verificação numérica exata de
    estabilidade de malha).
    """
    pid = PidController(PidGains(kp=5.0, ki=0.1, kd=0.0))
    readings = [50.0, 55.0, 60.0, 65.0, 68.0, 69.5]
    outputs = [pid.compute(setpoint=70.0, current_value=r, dt=1.0) for r in readings]
    # Saída geral deve tender a cair conforme o erro diminui.
    assert outputs[0] > outputs[-1]
    assert all(0.0 <= o <= 100.0 for o in outputs)
