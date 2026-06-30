from gpio.ds18b20_scan import scan, scan_with_readings


def make_sensor_dir(tmp_path, address: str, content: str):
    device_dir = tmp_path / address
    device_dir.mkdir()
    (device_dir / "w1_slave").write_text(content, encoding="ascii")


VALID_CONTENT = "4e 01 4b 46 7f ff 0e 10 68 : crc=68 YES\n4e 01 4b 46 7f ff 0e 10 68 t=20875\n"


def test_scan_finds_ds18b20_directories(tmp_path):
    make_sensor_dir(tmp_path, "28-aaa", VALID_CONTENT)
    make_sensor_dir(tmp_path, "28-bbb", VALID_CONTENT)
    # diretório de outra família de sensor 1-Wire (ex.: "10-" é DS18S20) — ignorado
    (tmp_path / "10-other-family").mkdir()

    addresses = scan(str(tmp_path))
    assert addresses == ["28-aaa", "28-bbb"]


def test_scan_returns_empty_list_when_base_path_missing(tmp_path):
    missing = tmp_path / "does_not_exist"
    assert scan(str(missing)) == []


def test_scan_returns_empty_list_when_no_sensors(tmp_path):
    assert scan(str(tmp_path)) == []


def test_scan_with_readings_includes_temperature(tmp_path):
    make_sensor_dir(tmp_path, "28-aaa", VALID_CONTENT)
    readings = scan_with_readings(str(tmp_path))
    assert readings == {"28-aaa": 20.875}


def test_scan_with_readings_reports_error_for_unreadable_sensor(tmp_path):
    bad_content = "garbage content not matching w1_slave format"
    make_sensor_dir(tmp_path, "28-bad", bad_content)
    readings = scan_with_readings(str(tmp_path))
    assert "erro de leitura" in readings["28-bad"]
