"""Validated local control settings; factory defaults are versioned separately."""
import copy
import json
import math
import os
import tempfile
from pathlib import Path

DEFAULTS_PATH = Path(__file__).parent / "data/control_defaults.json"
SETTINGS_PATH = Path(__file__).parent / "data/private/control_settings.json"


def factory_settings():
    return json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))


def validate_settings(raw):
    defaults = factory_settings()
    if not isinstance(raw, dict) or set(raw) != set(defaults):
        raise ValueError("Configuração deve conter exatamente os campos dos padrões de fábrica.")
    def number(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    curve = raw["mash_curve"]
    if not isinstance(curve, list) or len(curve) < 2:
        raise ValueError("Curva precisa de pelo menos dois pontos.")
    previous = None
    for point in curve:
        if not isinstance(point, list) or len(point) != 2 or not all(number(v) for v in point):
            raise ValueError("Pontos devem conter diferença em °C e potência numéricas finitas.")
        delta, power = point
        if not 0 <= power <= 100 or (previous and (delta <= previous[0] or power > previous[1])):
            raise ValueError("Temperaturas devem crescer e potências diminuir entre 0 e 100%.")
        previous = point
    if curve[-1][1] != 0:
        raise ValueError("O último ponto da curva deve cortar a potência em 0%.")
    for key in ("alert_above", "alert_clear", "boil_temperature", "boil_power"):
        if not number(raw[key]):
            raise ValueError(f"{key} deve ser numérico e finito.")
    if not 0 <= raw["alert_clear"] < raw["alert_above"]:
        raise ValueError("Retorno do alerta deve ser menor que o disparo e não negativo.")
    if not 50 <= raw["boil_temperature"] <= 110 or not 0 <= raw["boil_power"] <= 100:
        raise ValueError("Fervura: temperatura entre 50 e 110 °C; potência entre 0 e 100%.")
    if not isinstance(raw["freeze_hold_on_alert"], bool):
        raise ValueError("Congelar cronômetro deve ser booleano.")
    profiles = raw["vessel_profiles"]
    if not isinstance(profiles, dict) or any(not isinstance(k, str) or v not in ("mash", "boil") for k, v in profiles.items()):
        raise ValueError("Perfis por recipiente devem ser mash ou boil.")
    return copy.deepcopy(raw)


def load_settings(path=None):
    path = Path(path) if path is not None else SETTINGS_PATH
    return validate_settings(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else factory_settings()


def save_settings(raw, path=None):
    value = validate_settings(raw)
    path = Path(path) if path is not None else SETTINGS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".control-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return value


def power_limit(curve, delta):
    if delta <= curve[0][0]:
        return float(curve[0][1])
    for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
        if delta <= x1:
            return y0 + (y1 - y0) * (delta - x0) / (x1 - x0)
    return float(curve[-1][1])
