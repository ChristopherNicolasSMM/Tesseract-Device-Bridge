"""Conservative administrative diagnostics.

The diagnostic GPIO toggle is a *separate in-memory virtual bank*.
It never calls RealGPIOBackend, gpiozero, DeviceRuntime.set_actuator,
or changes a pin's operating mode. Physical pin scans and DS18B20
readings are observational only. Serial monitor is explicitly read-only.
"""
from __future__ import annotations

import re
from typing import Any

from gpio.ds18b20_scan import scan_with_readings


from reusable.serial_monitor import SerialError as DiagnosticError, SerialMonitor
from functools import lru_cache


BCM_PINS = tuple(range(2, 28))
_ROM_RE = re.compile(r"^28-[0-9a-fA-F]{12}$")


def sensors(config, *, read_fn=None):
    """Discover 1-Wire devices and associate ROM IDs to configured sensors."""
    discovered = (read_fn or scan_with_readings)()
    bound = {
        d.hardware.get("address"): d
        for d in config.devices
        if d.role == "sensor" and d.subtype == "temperature"
        and d.hardware.get("address")
    }
    return [
        {
            "address": address,
            "temperature_c": reading if isinstance(reading, (int, float)) else None,
            "error": reading if isinstance(reading, str) else None,
            "device_id": bound[address].id if address in bound else None,
            "device_name": bound[address].name if address in bound else None,
        }
        for address, reading in sorted(discovered.items())
        if _ROM_RE.fullmatch(address)
    ]


def gpio_inventory(config, runtime, virtual=None):
    """Logical values as reported by runtime, NOT electrical pin measurements."""
    virtual = virtual if virtual is not None else {}
    assigned = {}
    values = []
    for d in config.devices:
        pin = d.hardware.get("pin")
        if isinstance(pin, int):
            assigned.setdefault(pin, []).append(d.id)
        try:
            state = runtime.get_state(d.id)
            reading = state.value
        except (KeyError, ValueError) as exc:
            reading = None
        values.append({
            "id": d.id, "name": d.name, "pin": pin, "role": d.role,
            "subtype": d.subtype, "value": reading,
            "unit": d.unit, "risk": bool(d.is_risk),
        })
    return {
        "devices": values,
        "virtual_gpio": [
            {"pin": pin, "level": bool(virtual.get(pin, False)),
             "assigned_to": assigned.get(pin, [])}
            for pin in BCM_PINS
        ],
        "notice": (
            "Valores do runtime são estados lógicos, não leituras elétricas "
            "independentes. GPIO virtual não comanda hardware."
        ),
        "analog": (
            "Entradas analógicas são exibidas quando houver sensor/ADC "
            "configurado. Raspberry Pi não possui ADC nativo; use "
            "MCP3008/ADS1115 com driver apropriado."
        ),
    }


def virtual_gpio_write(config, state, *, pin, level):
    """Write virtual only, and never permit assigned pins."""
    if type(pin) is not int or pin not in BCM_PINS:
        raise DiagnosticError("GPIO BCM inválido; permitido 2 até 27.")
    if type(level) is not bool:
        raise DiagnosticError("Nível deve ser um booleano.")
    if any(d.hardware.get("pin") == pin for d in config.devices):
        raise DiagnosticError(
            "GPIO atribuído a um dispositivo. Diagnóstico virtual "
            "não altera saídas de produção."
        )
    state[pin] = level
    return {"pin": pin, "level": level, "mode": "virtual_only"}


@lru_cache(maxsize=1)
def serial_monitor():
    """Bridge adapter: core has no dependency on this project. One process owns ports."""
    return SerialMonitor()


def serial_ports():
    return serial_monitor().ports()


def serial_read(port_name, baudrate):
    """Compatibility API: bounded one-shot read via the reusable core."""
    monitor = serial_monitor()
    owner = object()
    opened = monitor.open(owner, port=port_name, baudrate=baudrate)
    try:
        return monitor.read(opened['session'], owner)
    finally:
        monitor.close_owner(owner)
