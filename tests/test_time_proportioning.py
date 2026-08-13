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


def test_duty_cycle_change_only_applies_at_next_window():
    """
    Correção: mudar o duty no meio de uma janela em andamento não pode
    afetar essa janela — só entra em vigor na próxima virada. Antes, o
    valor era aplicado na hora, o que criava um viés sistemático de
    "desliga antes da hora" sempre que o duty caía entre duas chamadas
    de should_be_on() (caso comum com PID se aproximando do alvo).
    """
    tpc = TimeProportioningController(window_seconds=10.0)
    tpc.set_duty_cycle(100.0)
    assert tpc.should_be_on(now=1000.0) is True  # janela 1 abre com duty=100%

    # duty cai para 0 no meio da janela 1 — não deve desligar agora.
    tpc.set_duty_cycle(0.0)
    assert tpc.should_be_on(now=1005.0) is True
    assert tpc.should_be_on(now=1009.9) is True

    # só na próxima janela o duty=0 pendente entra em vigor.
    assert tpc.should_be_on(now=1010.0) is False
    assert tpc.should_be_on(now=1015.0) is False


def test_duty_cycle_property_reflects_pending_value_immediately():
    """
    A property duty_cycle_percent (usada pela UI/medidor) mostra o
    último valor pedido via set_duty_cycle(), mesmo antes da virada de
    janela — só a decisão liga/desliga de should_be_on() é que fica
    travada até a próxima janela, não a leitura do valor "pendente".
    """
    tpc = TimeProportioningController(window_seconds=10.0)
    tpc.set_duty_cycle(100.0)
    tpc.should_be_on(now=1000.0)

    tpc.set_duty_cycle(30.0)
    assert tpc.duty_cycle_percent == 30.0  # já reflete o pedido novo
    assert tpc.should_be_on(now=1001.0) is True  # mas a janela atual ainda usa o duty travado (100%)


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


def test_force_lock_realigns_window_and_applies_duty_immediately():
    """
    force_lock() existe para transições de segurança (fail-safe,
    interruptor manual) que não podem esperar a janela atual acabar —
    ao contrário de set_duty_cycle(), tem efeito na mesma chamada.
    """
    tpc = TimeProportioningController(window_seconds=10.0)
    tpc.set_duty_cycle(100.0)
    assert tpc.should_be_on(now=1000.0) is True  # janela 1 abre com duty=100%
    assert tpc.should_be_on(now=1005.0) is True  # ainda no meio da janela 1

    tpc.force_lock(now=1005.0, duty_cycle_percent=0.0)
    assert tpc.should_be_on(now=1005.0) is False  # efeito imediato, sem esperar t=1010

    # a nova janela forçada em 1005.0 se comporta normalmente a partir daí.
    assert tpc.should_be_on(now=1014.9) is False  # ainda dentro da janela forçada (1005-1015)
    tpc.set_duty_cycle(100.0)
    assert tpc.should_be_on(now=1015.0) is True  # próxima janela, duty pendente aplicado


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
