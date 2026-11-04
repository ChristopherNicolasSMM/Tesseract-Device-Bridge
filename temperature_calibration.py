"""Calibração local por sensor: persistência privada e validação estrita.

Ajuste aditivo único em °C. Nunca altera dados crus de GPIO ou o arquivo
devices.yml. É aplicado somente na inicialização do DeviceRuntime, para
não trocar o significado da temperatura durante uma receita ativa.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path

from tesseract_bridge.infrastructure.paths import DATA_DIR
from storage import sqlite_store as store

DEFAULT_CALIBRATION_PATH = DATA_DIR / "private" / "sensor_calibration.json"
MAX_ABSOLUTE_OFFSET_C = 5.0


def _temperature_sensors(devices):
    return {device.id: device for device in devices
            if device.role == "sensor" and device.subtype == "temperature"}


def validate_calibrations(raw, devices):
    """Rejeita ajustes fora do domínio ou para um ROM ID diferente."""
    if not isinstance(raw, dict) or set(raw) != {"schema", "sensors"} or type(raw["schema"]) is not int or raw["schema"] != 1:
        raise ValueError("Calibração inválida: esperado schema=1 e sensors.")
    if not isinstance(raw["sensors"], dict):
        raise ValueError("Calibração inválida: sensors deve ser um objeto.")

    allowed = _temperature_sensors(devices)
    validated = {}
    for sensor_id, entry in raw["sensors"].items():
        if sensor_id not in allowed:
            raise ValueError(f"Calibração de sensor inexistente ou não térmico: {sensor_id!r}.")
        if not isinstance(entry, dict) or set(entry) != {"address", "offset_c"}:
            raise ValueError(f"{sensor_id}: esperado address e offset_c.")
        expected_address = allowed[sensor_id].hardware.get("address")
        if entry["address"] != expected_address or type(entry["address"]) != type(expected_address):
            raise ValueError(
                f"{sensor_id}: endereço físico mudou; recalibre o novo sensor antes de iniciar. "
                f"Esperado {expected_address!r}, encontrado {entry['address']!r}."
            )
        offset = entry["offset_c"]
        if type(offset) not in (float, int) or not math.isfinite(offset) or abs(offset) > MAX_ABSOLUTE_OFFSET_C:
            raise ValueError(
                f"{sensor_id}: offset deve ser finito, entre -{MAX_ABSOLUTE_OFFSET_C:g} e "
                f"+{MAX_ABSOLUTE_OFFSET_C:g} °C."
            )
        validated[sensor_id] = {"address": expected_address, "offset_c": float(offset)}
    return {"schema": 1, "sensors": validated}


def load_calibrations(devices, path=None):
    if path is None:
        return validate_calibrations(store.load_calibrations(), devices)
    path = Path(path)
    if not path.exists():
        return {"schema": 1, "sensors": {}}
    return validate_calibrations(json.loads(path.read_text(encoding="utf-8")), devices)


def save_calibrations(raw, devices, path=None):
    """Valida antes de gravar e substitui o JSON atomicamente."""
    result = validate_calibrations(raw, devices)
    if path is None:
        store.save_calibrations(result)
        return result
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".calibration-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return result
