"""Read-only admin diagnostics and isolated virtual GPIO tests."""
from __future__ import annotations

import pytest

from config import BridgeConfig
from device_runtime import DeviceRuntime
from gpio.simulated_backend import SimulatedGPIOBackend
from panel.app import create_panel_app
from storage import sqlite_store as store
from tesseract_bridge.diagnostics import service


@pytest.fixture
def app_client(monkeypatch):
    monkeypatch.setenv("TESSERACT_BRIDGE_ADMIN_TOKEN", "a-long-diagnostics-test-token")
    monkeypatch.setenv("TESSERACT_BRIDGE_SIMULATION_ONLY", "1")
    config = BridgeConfig.from_dict(store.load_config())
    runtime = DeviceRuntime(config, SimulatedGPIOBackend())
    app = create_panel_app(config, runtime)
    app.testing = True
    yield app.test_client(), config, runtime
    runtime.shutdown()


def auth():
    return {"X-Bridge-Admin-Token": "a-long-diagnostics-test-token"}


def test_scan_uses_1wire_rom_id_and_links_configured_sensor(app_client, monkeypatch):
    http, config, _runtime = app_client
    monkeypatch.setattr(service, "scan_with_readings", lambda: {
        "28-000000000001": 24.25,
        "28-000000000002": "erro de CRC",
        "fake_address": 13.0,
    })
    assert http.get("/api/admin/diagnostics/temperature").status_code == 401
    result = http.get("/api/admin/diagnostics/temperature", headers=auth())
    assert result.status_code == 200
    items = result.json["sensors"]
    assert len(items) == 2
    assert items[0]["address"] == "28-000000000001"
    assert items[0]["temperature_c"] == 24.25
    assert items[1]["error"] == "erro de CRC"


def test_gpio_inventory_is_logical_not_electrical(app_client):
    http, config, _runtime = app_client
    response = http.get("/api/admin/diagnostics/gpio", headers=auth())
    assert response.status_code == 200
    assert response.json["virtual_write_enabled"] is True
    assert "não leituras elétricas" in response.json["notice"]
    assert response.json["devices"]
    assert "ADC nativo" in response.json["analog"]


def test_virtual_gpio_rejects_assigned_pins_and_never_controls_runtime(app_client):
    http, config, runtime = app_client
    occupied = config.devices[0].hardware["pin"]
    refused = http.post("/api/admin/diagnostics/gpio/virtual",
        headers=auth(), json={"pin": occupied, "level": True})
    assert refused.status_code == 400
    available = next(pin for pin in service.BCM_PINS
        if all(d.hardware.get("pin") != pin for d in config.devices))
    result = http.post("/api/admin/diagnostics/gpio/virtual",
        headers=auth(), json={"pin": available, "level": True})
    assert result.status_code == 200, result.json
    assert result.json == {"pin": available, "level": True, "mode": "virtual_only"}
    assert all(not getattr(state, "is_risk", False) or not bool(state.value)
               for state in runtime.list_devices() if state.role == "actuator")


def test_virtual_gpio_requires_simulation_and_boolean(app_client, monkeypatch):
    http, config, _runtime = app_client
    available = next(pin for pin in service.BCM_PINS
        if all(d.hardware.get("pin") != pin for d in config.devices))
    malformed = http.post("/api/admin/diagnostics/gpio/virtual",
        headers=auth(), json={"pin": available, "level": 1})
    assert malformed.status_code == 400
    monkeypatch.setenv("TESSERACT_BRIDGE_SIMULATION_ONLY", "0")
    response = http.post("/api/admin/diagnostics/gpio/virtual",
        headers=auth(), json={"pin": available, "level": True})
    assert response.status_code == 403


def test_serial_ports_are_read_only_and_require_admin(app_client, monkeypatch):
    http, _, _runtime = app_client
    monkeypatch.setattr(service, "serial_ports", lambda: {
        "available": True,
        "ports": [{"device": "MOCK0", "description": "Test adapter"}],
        "message": "Somente leitura.",
    })
    assert http.get("/api/admin/diagnostics/serial/ports").status_code == 401
    res = http.get("/api/admin/diagnostics/serial/ports", headers=auth())
    assert res.status_code == 200
    assert res.json["ports"][0]["device"] == "MOCK0"


def test_serial_read_uses_explicit_bounded_service(app_client, monkeypatch):
    http, _, _runtime = app_client
    monkeypatch.setattr(service, "serial_read",
        lambda port, baudrate: {"port": port, "baudrate": baudrate,
                                 "text": "ok", "bytes_read": 2, "mode": "read_only"})
    result = http.post("/api/admin/diagnostics/serial/read", headers=auth(),
        json={"port": "MOCK0", "baudrate": 9600})
    assert result.status_code == 200
    assert result.json["text"] == "ok"


def test_admin_form_has_live_reference_selects():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    html = (root / "panel/templates/index.html").read_text(encoding="utf8")
    js = (root / "panel/static/admin-sqlite.js").read_text(encoding="utf8")
    for name in ("pin", "temperature_sensor", "controller_device"):
        assert '<select name="'+name+'"' in html
    for section in ("sqlScanTemp", "sqlVirtualOn", "sqlVirtualOff", "sqlSerialRead"):
        assert 'id="'+section+'"' in html
        assert section in js
    assert "refreshReferences(d)" in js
    assert "diagnostics/gpio/virtual" in js
