import os

import pytest

from run_panel import ensure_config_file
from config import ConfigError


def test_ensure_config_file_creates_from_example_when_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    example_content = "backend: simulated\nmqtt:\n  enabled: false\npanel:\n  enabled: true\ndevices: []\n"
    (tmp_path / "devices.yml.example").write_text(example_content, encoding="utf-8")

    assert not (tmp_path / "devices.yml").exists()
    ensure_config_file("devices.yml")

    assert (tmp_path / "devices.yml").exists()
    assert (tmp_path / "devices.yml").read_text(encoding="utf-8") == example_content


def test_ensure_config_file_does_not_overwrite_existing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    (tmp_path / "devices.yml.example").write_text("backend: simulated\n", encoding="utf-8")
    (tmp_path / "devices.yml").write_text("backend: real\n", encoding="utf-8")

    ensure_config_file("devices.yml")

    assert (tmp_path / "devices.yml").read_text(encoding="utf-8") == "backend: real\n"


def test_ensure_config_file_raises_when_example_also_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ConfigError, match="modelo padrão"):
        ensure_config_file("devices.yml")


def test_ensure_config_file_creates_parent_dirs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    (tmp_path / "devices.yml.example").write_text("backend: simulated\n", encoding="utf-8")
    nested_path = "config/nested/devices.yml"

    ensure_config_file(nested_path)

    assert (tmp_path / nested_path).exists()
