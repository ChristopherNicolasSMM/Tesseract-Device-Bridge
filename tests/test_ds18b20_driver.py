import time

import pytest

from gpio.ds18b20_driver import Ds18b20Reader, Ds18b20ReadError

# Intervalo bem curto pra thread de fundo não deixar os testes lentos --
# não tem nada a ver com o default real de produção (1.0s).
FAST_POLL = 0.01
# Tempo de sobra pra garantir que a thread de fundo já rodou pelo menos
# um ciclo depois de FAST_POLL -- generoso o bastante pra não flakar
# mesmo numa máquina de CI carregada.
SETTLE = 0.08


def make_w1_dir(tmp_path, address: str, content: str):
    device_dir = tmp_path / address
    device_dir.mkdir()
    (device_dir / "w1_slave").write_text(content, encoding="ascii")
    return tmp_path


VALID_CONTENT = "4e 01 4b 46 7f ff 0e 10 68 : crc=68 YES\n4e 01 4b 46 7f ff 0e 10 68 t=20875\n"
INVALID_CRC_CONTENT = "4e 01 4b 46 7f ff 0e 10 68 : crc=68 NO\n4e 01 4b 46 7f ff 0e 10 68 t=20875\n"
MISSING_T_CONTENT = "4e 01 4b 46 7f ff 0e 10 68 : crc=68 YES\n4e 01 4b 46 7f ff 0e 10 68\n"
GARBAGE_CONTENT = "isto nao eh um arquivo w1_slave valido"


@pytest.fixture
def make_reader():
    """
    Fábrica de Ds18b20Reader que garante close() no final de cada teste
    -- sem isso, a thread de fundo (daemon=True) continuaria rodando
    solta até o processo de teste inteiro terminar.
    """
    readers = []

    def _make(**kwargs):
        kwargs.setdefault("poll_interval_seconds", FAST_POLL)
        reader = Ds18b20Reader(**kwargs)
        readers.append(reader)
        return reader

    yield _make

    for reader in readers:
        reader.close()


def test_read_valid_w1_slave_returns_celsius(tmp_path, make_reader):
    base = make_w1_dir(tmp_path, "28-aaa", VALID_CONTENT)
    reader = make_reader(pin=4, address="28-aaa", base_path=str(base))
    assert reader.value == 20.875


def test_read_negative_temperature(tmp_path, make_reader):
    content = "4e 01 4b 46 7f ff 0e 10 68 : crc=68 YES\n4e 01 4b 46 7f ff 0e 10 68 t=-500\n"
    base = make_w1_dir(tmp_path, "28-bbb", content)
    reader = make_reader(pin=4, address="28-bbb", base_path=str(base))
    assert reader.value == -0.5


def test_missing_device_directory_raises_on_construction(tmp_path):
    """
    A primeira leitura é síncrona, dentro de __init__ -- um sensor
    ausente falha JÁ na construção (fail-fast no boot), não só quando
    alguém acessar .value depois.
    """
    with pytest.raises(Ds18b20ReadError, match="não encontrado"):
        Ds18b20Reader(pin=4, address="28-does-not-exist", base_path=str(tmp_path))


def test_invalid_crc_raises_on_construction(tmp_path):
    base = make_w1_dir(tmp_path, "28-ccc", INVALID_CRC_CONTENT)
    with pytest.raises(Ds18b20ReadError, match="CRC inválido"):
        Ds18b20Reader(pin=4, address="28-ccc", base_path=str(base))


def test_missing_t_field_raises_on_construction(tmp_path):
    base = make_w1_dir(tmp_path, "28-ddd", MISSING_T_CONTENT)
    with pytest.raises(Ds18b20ReadError, match="t="):
        Ds18b20Reader(pin=4, address="28-ddd", base_path=str(base))


def test_garbage_content_raises_on_construction(tmp_path):
    base = make_w1_dir(tmp_path, "28-eee", GARBAGE_CONTENT)
    with pytest.raises(Ds18b20ReadError):
        Ds18b20Reader(pin=4, address="28-eee", base_path=str(base))


def test_accepts_extra_kwargs_without_error(tmp_path, make_reader):
    """
    RealGPIOBackend.setup() repassa todos os kwargs do devices.yml
    (min, max, driver, etc.) para o driver — Ds18b20Reader precisa
    aceitar e ignorar o que não usa, sem TypeError de argumento
    inesperado.
    """
    base = make_w1_dir(tmp_path, "28-ggg", VALID_CONTENT)
    reader = make_reader(
        pin=4, address="28-ggg", base_path=str(base),
        driver="ds18b20", min=0, max=120,
    )
    assert reader.value == 20.875


# ---- thread de fundo: cache, atualização eventual, resiliência a erro ----


def test_value_is_cached_updates_only_on_next_poll_cycle(tmp_path, make_reader):
    """
    Comportamento novo (era "sem cache, relê a cada chamada" antes):
    .value não relê o arquivo na hora -- devolve o que a thread de
    fundo tem em cache, atualizado a cada poll_interval_seconds.
    """
    base = make_w1_dir(tmp_path, "28-fff", VALID_CONTENT)
    reader = make_reader(pin=4, address="28-fff", base_path=str(base))
    assert reader.value == 20.875  # da leitura síncrona inicial

    (base / "28-fff" / "w1_slave").write_text(
        "4e 01 4b 46 7f ff 0e 10 68 : crc=68 YES\n4e 01 4b 46 7f ff 0e 10 68 t=22000\n",
        encoding="ascii",
    )
    time.sleep(SETTLE)
    assert reader.value == 22.0  # agora sim, depois de pelo menos 1 ciclo de poll


def test_transient_read_failure_keeps_last_good_value_cached(tmp_path, make_reader):
    """
    Um glitch de CRC (comum em 1-Wire por ruído elétrico) na thread de
    fundo não deve derrubar .value nem travar o valor bom anterior --
    só loga e tenta de novo no próximo ciclo.
    """
    base = make_w1_dir(tmp_path, "28-hhh", VALID_CONTENT)
    reader = make_reader(pin=4, address="28-hhh", base_path=str(base))
    assert reader.value == 20.875

    (base / "28-hhh" / "w1_slave").write_text(INVALID_CRC_CONTENT, encoding="ascii")
    time.sleep(SETTLE)
    assert reader.value == 20.875  # sem exceção, valor bom anterior mantido

    (base / "28-hhh" / "w1_slave").write_text(VALID_CONTENT, encoding="ascii")
    time.sleep(SETTLE)
    assert reader.value == 20.875  # se recupera sozinho no próximo ciclo bom


def test_value_raises_when_stale_after_seconds_exceeded(tmp_path, make_reader):
    """
    Se a thread de fundo ficar falhando por tempo demais (sensor
    desconectado de verdade, não só um glitch), .value passa a
    levantar em vez de servir um valor cada vez mais velho pra sempre.
    """
    base = make_w1_dir(tmp_path, "28-iii", VALID_CONTENT)
    reader = make_reader(
        pin=4, address="28-iii", base_path=str(base),
        stale_after_seconds=0.03,
    )
    assert reader.value == 20.875

    (base / "28-iii" / "w1_slave").unlink()
    (base / "28-iii").rmdir()

    time.sleep(0.15)  # bem além de stale_after_seconds (0.03s)
    with pytest.raises(Ds18b20ReadError, match="sem leitura válida há"):
        _ = reader.value


def test_close_stops_background_thread(tmp_path, make_reader):
    base = make_w1_dir(tmp_path, "28-jjj", VALID_CONTENT)
    reader = make_reader(pin=4, address="28-jjj", base_path=str(base))
    assert reader._thread.is_alive() is True

    reader.close()
    assert reader._thread.is_alive() is False
