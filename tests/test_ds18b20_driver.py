import pytest

from gpio.ds18b20_driver import Ds18b20Reader, Ds18b20ReadError


def make_w1_dir(tmp_path, address: str, content: str):
    device_dir = tmp_path / address
    device_dir.mkdir()
    (device_dir / "w1_slave").write_text(content, encoding="ascii")
    return tmp_path


VALID_CONTENT = "4e 01 4b 46 7f ff 0e 10 68 : crc=68 YES\n4e 01 4b 46 7f ff 0e 10 68 t=20875\n"
INVALID_CRC_CONTENT = "4e 01 4b 46 7f ff 0e 10 68 : crc=68 NO\n4e 01 4b 46 7f ff 0e 10 68 t=20875\n"
MISSING_T_CONTENT = "4e 01 4b 46 7f ff 0e 10 68 : crc=68 YES\n4e 01 4b 46 7f ff 0e 10 68\n"
GARBAGE_CONTENT = "isto nao eh um arquivo w1_slave valido"


def test_read_valid_w1_slave_returns_celsius(tmp_path):
    base = make_w1_dir(tmp_path, "28-aaa", VALID_CONTENT)
    reader = Ds18b20Reader(pin=4, address="28-aaa", base_path=str(base))
    assert reader.value == 20.875


def test_read_negative_temperature(tmp_path):
    content = "4e 01 4b 46 7f ff 0e 10 68 : crc=68 YES\n4e 01 4b 46 7f ff 0e 10 68 t=-500\n"
    base = make_w1_dir(tmp_path, "28-bbb", content)
    reader = Ds18b20Reader(pin=4, address="28-bbb", base_path=str(base))
    assert reader.value == -0.5


def test_missing_device_directory_raises_ds18b20_read_error(tmp_path):
    reader = Ds18b20Reader(pin=4, address="28-does-not-exist", base_path=str(tmp_path))
    with pytest.raises(Ds18b20ReadError, match="não encontrado"):
        _ = reader.value


def test_invalid_crc_raises_ds18b20_read_error(tmp_path):
    base = make_w1_dir(tmp_path, "28-ccc", INVALID_CRC_CONTENT)
    reader = Ds18b20Reader(pin=4, address="28-ccc", base_path=str(base))
    with pytest.raises(Ds18b20ReadError, match="CRC inválido"):
        _ = reader.value


def test_missing_t_field_raises_ds18b20_read_error(tmp_path):
    base = make_w1_dir(tmp_path, "28-ddd", MISSING_T_CONTENT)
    reader = Ds18b20Reader(pin=4, address="28-ddd", base_path=str(base))
    with pytest.raises(Ds18b20ReadError, match="t="):
        _ = reader.value


def test_garbage_content_raises_ds18b20_read_error(tmp_path):
    base = make_w1_dir(tmp_path, "28-eee", GARBAGE_CONTENT)
    reader = Ds18b20Reader(pin=4, address="28-eee", base_path=str(base))
    with pytest.raises(Ds18b20ReadError):
        _ = reader.value


def test_each_call_to_value_rereads_file(tmp_path):
    """
    .value não deve cachear — cada leitura tem que refletir o conteúdo
    atual do arquivo (o kernel atualiza w1_slave a cada ciclo de
    conversão do sensor, ~750ms).
    """
    base = make_w1_dir(tmp_path, "28-fff", VALID_CONTENT)
    reader = Ds18b20Reader(pin=4, address="28-fff", base_path=str(base))
    assert reader.value == 20.875

    (base / "28-fff" / "w1_slave").write_text(
        "4e 01 4b 46 7f ff 0e 10 68 : crc=68 YES\n4e 01 4b 46 7f ff 0e 10 68 t=22000\n",
        encoding="ascii",
    )
    assert reader.value == 22.0


def test_accepts_extra_kwargs_without_error(tmp_path):
    """
    RealGPIOBackend.setup() repassa todos os kwargs do devices.yml
    (min, max, etc.) para o driver — Ds18b20Reader precisa aceitar e
    ignorar o que não usa, sem TypeError de argumento inesperado.
    """
    base = make_w1_dir(tmp_path, "28-ggg", VALID_CONTENT)
    reader = Ds18b20Reader(
        pin=4, address="28-ggg", base_path=str(base),
        driver="ds18b20", min=0, max=120,
    )
    assert reader.value == 20.875
