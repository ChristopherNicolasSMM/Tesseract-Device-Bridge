import pytest

from time_proportioning import TimeProportioningController


def test_zero_duty_cycle_always_off():
    tpc = TimeProportioningController(window_seconds=10.0)
    tpc.set_duty_cycle(0.0)
    assert tpc.should_be_on(now=1000.0) is False
    assert tpc.should_be_on(now=1005.0) is False
    assert tpc.should_be_on(now=1009.9) is False


def test_full_duty_cycle_always_on():
    tpc = TimeProportioningController(window_seconds=10.0)
    tpc.set_duty_cycle(100.0)
    assert tpc.should_be_on(now=1000.0) is True
    assert tpc.should_be_on(now=1005.0) is True
    assert tpc.should_be_on(now=1009.9) is True


def test_fifty_percent_duty_cycle_on_first_half_off_second_half():
    tpc = TimeProportioningController(window_seconds=10.0)
    tpc.set_duty_cycle(50.0)
    assert tpc.should_be_on(now=1000.0) is True
    assert tpc.should_be_on(now=1004.9) is True
    assert tpc.should_be_on(now=1005.1) is False
    assert tpc.should_be_on(now=1009.9) is False


def test_window_advances_after_window_seconds():
    tpc = TimeProportioningController(window_seconds=10.0)
    tpc.set_duty_cycle(65.0)
    assert tpc.should_be_on(now=1000.0) is True   # janela 1, t=0
    assert tpc.should_be_on(now=1006.0) is True   # janela 1, t=6 (< 6.5)
    assert tpc.should_be_on(now=1007.0) is False  # janela 1, t=7 (> 6.5)

    # nova janela começa em now=1010 (10s desde o início da janela 1)
    assert tpc.should_be_on(now=1010.0) is True   # janela 2, t=0 relativo


def test_duty_cycle_change_applies_to_current_window_immediately():
    tpc = TimeProportioningController(window_seconds=10.0)
    tpc.set_duty_cycle(0.0)
    assert tpc.should_be_on(now=1000.0) is False

    tpc.set_duty_cycle(100.0)
    assert tpc.should_be_on(now=1001.0) is True  # ainda na mesma janela, mas duty mudou


def test_duty_cycle_clamped_to_0_100():
    tpc = TimeProportioningController(window_seconds=10.0)
    tpc.set_duty_cycle(150.0)
    assert tpc.should_be_on(now=1000.0) is True
    assert tpc.should_be_on(now=1009.9) is True  # se não clampasse, "150%" ligaria o tempo todo mesmo assim, mas confirma o clamp não quebra

    tpc.set_duty_cycle(-50.0)
    tpc.reset()
    assert tpc.should_be_on(now=2000.0) is False


def test_reset_realigns_window():
    tpc = TimeProportioningController(window_seconds=10.0)
    tpc.set_duty_cycle(50.0)
    tpc.should_be_on(now=1000.0)
    tpc.should_be_on(now=1004.0)

    tpc.reset()
    tpc.set_duty_cycle(50.0)
    # depois do reset, a janela deveria recomeçar a partir do próximo now()
    assert tpc.should_be_on(now=5000.0) is True  # início de nova janela, dentro do duty


def test_invalid_window_seconds_raises_value_error():
    with pytest.raises(ValueError):
        TimeProportioningController(window_seconds=0)
    with pytest.raises(ValueError):
        TimeProportioningController(window_seconds=-5)


def test_multiple_consecutive_windows_at_partial_duty_cycle():
    tpc = TimeProportioningController(window_seconds=4.0)
    tpc.set_duty_cycle(25.0)  # 1s ligado, 3s desligado, a cada 4s

    results = [tpc.should_be_on(now=t) for t in [0.0, 0.9, 1.1, 3.9, 4.0, 4.9, 5.1]]
    assert results == [True, True, False, False, True, True, False]
