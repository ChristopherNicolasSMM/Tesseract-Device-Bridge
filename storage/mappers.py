"""Typed translations between validated runtime dictionaries and ORM entities.

No direct SQL execution or device actuation occurs in this module.
Unsupported keys and nested data fail closed rather than being discarded.
"""
from __future__ import annotations

from sqlalchemy import select
from config import BridgeConfig
from storage.models import (
    BridgeSettings, MqttSettings, PanelSettings, Device, DeviceProperty,
    DeviceHeatingSource, Recipe, RecipeVessel, RecipeStep, RecipeStepPump,
    RecipeHopAlarm, ControlProfile, ControlCurvePoint, ControlVesselProfile,
)


class NormalizationError(RuntimeError):
    pass


def _expect_fields(value, allowed, location):
    if not isinstance(value, dict):
        raise NormalizationError(f"{location} deve ser um objeto.")
    unknown = set(value) - set(allowed)
    if unknown:
        raise NormalizationError(f"{location}: campo(s) não mapeado(s): {sorted(unknown)}. "
                                 "Migração recusada para evitar perda de informação.")


def _scalar_encode(value):
    if value is None:
        return "null", None
    if type(value) is bool:
        return "bool", "1" if value else "0"
    if type(value) is int:
        return "int", str(value)
    if type(value) is float:
        return "float", repr(value)
    if isinstance(value, str):
        return "str", value
    raise NormalizationError(
        f"Propriedade aninhada/não escalar {type(value).__name__}: "
        "crie coluna/modelo próprio antes de importar; não converter em JSON opaco."
    )


def _scalar_decode(kind, value):
    if kind == "null":
        return None
    if kind == "bool":
        return value == "1"
    if kind == "int":
        return int(value)
    if kind == "float":
        return float(value)
    if kind == "str":
        return value
    raise NormalizationError("Tipo não reconhecido na coluna tipada: " + str(kind))


def _add_properties(entity, namespace, entries):
    for key, value in entries.items():
        kind, text = _scalar_encode(value)
        entity.properties.append(
            DeviceProperty(namespace=namespace, key=key, value_kind=kind, value_text=text)
        )


def _device_to_orm(raw, position):
    if not isinstance(raw, dict):
        raise NormalizationError("device deve ser um objeto.")
    hw = raw.get("hardware", {})
    if not isinstance(hw, dict):
        raise NormalizationError(f"hardware de {raw['id']} deve ser objeto.")
    failsafe_kind = None
    failsafe_text = None
    if "failsafe_value" in raw:
        failsafe_kind, failsafe_text = _scalar_encode(raw["failsafe_value"])
    item = Device(
        id=raw["id"], position=position, name=raw["name"],
        role=raw["role"], subtype=raw.get("subtype"), unit=raw.get("unit"),
        state_topic=raw.get("state_topic"), command_topic=raw.get("command_topic"),
        is_risk=raw.get("is_risk", False), is_risk_present="is_risk" in raw,
        simulated_present="simulated" in raw, limits_present="limits" in raw,
        failsafe_kind=failsafe_kind, failsafe_text=failsafe_text,
        failsafe_timeout_seconds=raw.get("failsafe_timeout_seconds"),
        pin=hw["pin"], driver=hw.get("driver"), address=hw.get("address"),
        window_seconds=hw.get("window_seconds"),
        active_high=hw.get("active_high"), remote_control=hw.get("remote_control"),
        external_control_policy=hw.get("external_control_policy"),
    )
    if "heating_source" in hw:
        source = hw["heating_source"]
        if not isinstance(source, dict):
            raise NormalizationError(f"heating_source de {raw['id']} deve ser objeto.")
        item.heating_source = DeviceHeatingSource(
            participation=source["participation"],
            temperature_sensor=source["temperature_sensor"],
            controller_device=source.get("controller_device"),
            external_flame_cutoff=source["external_flame_cutoff"],
        )
    hardware_columns = {
        "pin", "driver", "address", "window_seconds", "active_high",
        "remote_control", "external_control_policy", "heating_source",
    }
    _add_properties(item, "hardware", {key: value for key, value in hw.items()
                                        if key not in hardware_columns})
    if "heating_source" in hw:
        _add_properties(item, "heating_source", {
            key: value for key, value in hw["heating_source"].items()
            if key not in {"participation", "temperature_sensor",
                           "controller_device", "external_flame_cutoff"}
        })
    known_device_fields = {
        "id", "name", "role", "subtype", "unit", "state_topic",
        "command_topic", "hardware", "simulated", "limits",
        "failsafe_value", "is_risk", "failsafe_timeout_seconds",
    }
    _add_properties(item, "device", {key: value for key, value in raw.items()
                                     if key not in known_device_fields})
    for namespace in ("simulated", "limits"):
        source = raw.get(namespace, {})
        if not isinstance(source, dict):
            raise NormalizationError(f"device {raw['id']}: {namespace} inválido.")
        _add_properties(item, namespace, source)
    return item


def _device_to_dict(item):
    hw = {"pin": item.pin}
    for name in ("driver", "address", "window_seconds", "active_high",
                 "remote_control", "external_control_policy"):
        value = getattr(item, name)
        if value is not None:
            hw[name] = value
    if item.heating_source is not None:
        h = item.heating_source
        hw["heating_source"] = {
            "participation": h.participation,
            "temperature_sensor": h.temperature_sensor,
            "external_flame_cutoff": bool(h.external_flame_cutoff),
        }
        if h.controller_device is not None:
            hw["heating_source"]["controller_device"] = h.controller_device
    result = dict(id=item.id, name=item.name, role=item.role, hardware=hw)
    for name in ("subtype", "unit", "state_topic", "command_topic",
                 "failsafe_timeout_seconds"):
        val = getattr(item, name)
        if val is not None:
            result[name] = val
    if item.failsafe_kind is not None:
        result["failsafe_value"] = _scalar_decode(item.failsafe_kind, item.failsafe_text)
    if item.is_risk_present:
        result["is_risk"] = bool(item.is_risk)
    for name, present in (("simulated", item.simulated_present), ("limits", item.limits_present)):
        if present:
            result[name] = {}
    for prop in item.properties:
        if prop.namespace == "hardware":
            namespace = hw
        elif prop.namespace == "heating_source":
            namespace = hw["heating_source"]
        elif prop.namespace == "device":
            namespace = result
        else:
            namespace = result.setdefault(prop.namespace, {})
        namespace[prop.key] = _scalar_decode(prop.value_kind, prop.value_text)
    return result


def _config_to_orm(session, raw, revision):
    _expect_fields(raw, {"backend", "mqtt", "panel", "devices"}, "configuração do Bridge")
    _expect_fields(raw.get("mqtt", {}), {
        "enabled", "host", "port", "username", "password", "client_id",
        "topic_prefix", "reconnect_interval_seconds",
    }, "configuração MQTT")
    _expect_fields(raw.get("panel", {}), {"enabled", "host", "port"}, "configuração do painel")
    parsed = BridgeConfig.from_dict(raw)
    parsed.validate()
    m, p = parsed.mqtt, parsed.panel
    session.add(BridgeSettings(id=1, backend=parsed.backend, revision=revision))
    session.add(MqttSettings(
        id=1, enabled=m.enabled, host=m.host, port=m.port, username=m.username,
        password=m.password, client_id=m.client_id, topic_prefix=m.topic_prefix,
        reconnect_interval_seconds=m.reconnect_interval_seconds,
    ))
    session.add(PanelSettings(id=1, enabled=p.enabled, host=p.host, port=p.port))
    for i, device in enumerate(raw["devices"]):
        session.add(_device_to_orm(device, i))
    return parsed


def _config_from_orm(session):
    s = session.get(BridgeSettings, 1)
    m = session.get(MqttSettings, 1)
    p = session.get(PanelSettings, 1)
    if s is None or m is None or p is None:
        raise NormalizationError("Cabeçalho relacional incompleto.")
    config = {
        "backend": s.backend,
        "mqtt": {
            "enabled": bool(m.enabled), "host": m.host, "port": m.port,
            "username": m.username, "password": m.password,
            "client_id": m.client_id, "topic_prefix": m.topic_prefix,
            "reconnect_interval_seconds": m.reconnect_interval_seconds,
        },
        "panel": {"enabled": bool(p.enabled), "host": p.host, "port": p.port},
        "devices": [],
    }
    for device in session.scalars(select(Device).order_by(Device.position)):
        config["devices"].append(_device_to_dict(device))
    return config


def _populate_recipe_children(item, raw):
    """Fill a *managed* Recipe with typed children, never create a second parent.

    For an update the managed row and its identity key must be preserved:
    active_recipe points at that same primary key. Fresh children can only
    be attached after old collections have been flushed/deleted.
    """
    _expect_fields(raw, {"name", "vessels", "steps"}, f"receita {item.id}")
    for position, v in enumerate(raw["vessels"]):
        _expect_fields(v, {
            "id", "name", "heater_device_id", "sensor_device_id", "pid", "order",
        }, f"vasilha {v.get('id')}")
        _expect_fields(v["pid"], {"kp", "ki", "kd"}, f"PID da vasilha {v['id']}")
        item.vessels.append(RecipeVessel(
            id=v["id"], position=position, name=v["name"],
            heater_device_id=v["heater_device_id"],
            sensor_device_id=v["sensor_device_id"],
            kp=v["pid"]["kp"], ki=v["pid"]["ki"], kd=v["pid"]["kd"],
            display_order=v.get("order"),
        ))
    for position, step in enumerate(raw["steps"]):
        _expect_fields(step, {
            "vessel", "target_temp", "hold_minutes", "pumps", "label", "hop_alarms",
        }, f"etapa {position} da receita {item.id}")
        entry = RecipeStep(
            position=position, vessel_id=step["vessel"], target_temp=step["target_temp"],
            hold_minutes=step["hold_minutes"], label=step.get("label"),
        )
        for order, pump in enumerate(step.get("pumps", [])):
            entry.pumps.append(RecipeStepPump(position=order, device_id=pump))
        for order, alarm in enumerate(step.get("hop_alarms", [])):
            _expect_fields(alarm, {"minutes_remaining", "label"}, f"alarme {order}")
            entry.hop_alarms.append(RecipeHopAlarm(
                position=order, minutes_remaining=alarm["minutes_remaining"],
                label=alarm["label"]
            ))
        item.steps.append(entry)
    return item


def _recipe_to_orm(row, raw):
    item = Recipe(
        id=row["id"], source=row["source"], editable=bool(row["editable"]),
        name=raw["name"], revision=row["revision"],
    )
    return _populate_recipe_children(item, raw)


def _recipe_from_orm(item):
    data = {"name": item.name, "vessels": [], "steps": []}
    for v in item.vessels:
        row = {
            "id": v.id, "name": v.name, "heater_device_id": v.heater_device_id,
            "sensor_device_id": v.sensor_device_id,
            "pid": {"kp": v.kp, "ki": v.ki, "kd": v.kd},
        }
        if v.display_order is not None:
            row["order"] = v.display_order
        data["vessels"].append(row)
    for s in item.steps:
        row = {
            "vessel": s.vessel_id, "target_temp": s.target_temp,
            "hold_minutes": s.hold_minutes,
        }
        if s.label is not None:
            row["label"] = s.label
        if s.pumps:
            row["pumps"] = [p.device_id for p in s.pumps]
        if s.hop_alarms:
            row["hop_alarms"] = [
                {"minutes_remaining": h.minutes_remaining, "label": h.label}
                for h in s.hop_alarms
            ]
        data["steps"].append(row)
    return data


def _control_to_orm(key, raw, revision):
    _expect_fields(raw, {
        "mash_curve", "alert_above", "alert_clear", "freeze_hold_on_alert",
        "boil_temperature", "boil_power", "vessel_profiles",
    }, f"parâmetros {key}")
    item = ControlProfile(
        key=key, revision=revision, alert_above=raw["alert_above"],
        alert_clear=raw["alert_clear"],
        freeze_hold_on_alert=raw["freeze_hold_on_alert"],
        boil_temperature=raw["boil_temperature"], boil_power=raw["boil_power"],
    )
    for pos, (delta, power) in enumerate(raw["mash_curve"]):
        item.curve.append(ControlCurvePoint(position=pos, delta=delta, power=power))
    for vessel_id, profile in raw["vessel_profiles"].items():
        item.vessel_profiles.append(ControlVesselProfile(vessel_id=vessel_id, profile=profile))
    return item


def _control_from_orm(item):
    return {
        "mash_curve": [[point.delta, point.power] for point in item.curve],
        "alert_above": item.alert_above, "alert_clear": item.alert_clear,
        "freeze_hold_on_alert": bool(item.freeze_hold_on_alert),
        "boil_temperature": item.boil_temperature, "boil_power": item.boil_power,
        "vessel_profiles": {entry.vessel_id: entry.profile for entry in item.vessel_profiles},
    }


