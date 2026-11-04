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


class DiagnosticError(ValueError):
    pass


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


def serial_ports():
    """List OS-registered ports. pyserial is an optional diagnostic extra."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return {"available": False, "ports": [], "message":
                "Monitor serial opcional. Instale pyserial no ambiente de diagnóstico."}
    return {
        "available": True,
        "ports": [
            {"device": port.device, "description": port.description}
            for port in list_ports.comports()
        ],
        "message": (
            "Leitura serial apenas sob solicitação, sem comandos de escrita. "
            "Abrir uma porta pode reiniciar alguns microcontroladores."
        ),
    }


def serial_read(port_name, baudrate):
    """Bounded, explicit, read-only poll; port must be enumerated by the OS."""
    try:
        from serial import Serial
    except ImportError as exc:
        raise DiagnosticError("Instale pyserial para habilitar o monitor.") from exc
    ports = {entry["device"] for entry in serial_ports()["ports"]}
    if port_name not in ports:
        raise DiagnosticError("Porta não encontrada na lista de dispositivos.")
    if type(baudrate) is not int or baudrate not in (9600, 19200, 38400, 57600, 115200):
        raise DiagnosticError("Baud rate não suportado.")
    connection = Serial(port=None, baudrate=baudrate, timeout=0.2)
    try:
        # Request no serial control signals. Certain devices can still reset
        # on open due to their USB bridge: show this warning in the UI.
        connection.dtr = False
        connection.rts = False
        connection.port = port_name
        connection.open()
        chunk = connection.read(1024)
    except Exception as exc:
        raise DiagnosticError("Falha na leitura serial: " + str(exc)) from exc
    finally:
        connection.close()
    return {"port": port_name, "baudrate": baudrate,
            "text": chunk.decode("utf-8", errors="replace"),
            "bytes_read": len(chunk), "mode": "read_only"}
