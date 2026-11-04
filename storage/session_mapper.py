"""Strict translation of legacy operational state to normalized SQLAlchemy.

Only used by the copy migrator for now. No physical actuator commands and no
runtime dual-writes. A session's control profile is an immutable snapshot of
that execution, distinct from editable next-session control settings.
"""
from __future__ import annotations

from recipe_engine.state import RecipeState
from temperature_calibration import validate_calibrations
from storage import sqlite_store as store
from storage.models import (
    ActiveRecipe, SensorCalibration, SessionState, SessionFieldPresence,
    SessionAlarm, SessionFiredHopKey,
)
from storage.mappers import (
    NormalizationError, _control_to_orm, _control_from_orm, _expect_fields,
)


def read_operational_snapshot(path, *, devices):
    """Read only; preserve every column including calibration timestamps."""
    with store.connection(path=path) as conn:
        active = conn.execute(
            "SELECT id, recipe_id FROM active_recipe WHERE id=1"
        ).fetchone()
        calibration = [dict(r) for r in conn.execute(
            "SELECT sensor_id,address,offset_c,updated_at "
            "FROM sensor_calibrations ORDER BY sensor_id"
        )]
        state_row = conn.execute(
            "SELECT id, state_json, updated_at FROM session_state WHERE id=1"
        ).fetchone()
    result = {
        "active_recipe": dict(active) if active is not None else None,
        "calibrations": calibration,
        "state": json.loads(state_row["state_json"]) if state_row else None,
        "session_updated_at": state_row["updated_at"] if state_row else None,
    }
    validate_calibrations({
        "schema": 1, "sensors": {
            row["sensor_id"]: {
                "address": row["address"], "offset_c": row["offset_c"]
            } for row in calibration
        }
    }, devices)
    if result["state"] is not None:
        _validate_session_payload(result["state"])
    return result


def _validate_session_payload(raw):
    fields = set(RecipeState.__dataclass_fields__)
    _expect_fields(raw, fields, "session_state")
    try:
        parsed = RecipeState(**raw)
    except (ValueError, TypeError, KeyError) as exc:
        raise NormalizationError("Estado de sessão inválido: " + str(exc)) from exc
    if raw.get("control_settings") is not None:
        _control_to_orm("session_snapshot:1", raw["control_settings"], 1)
    # We do not rewrite persisted alarm IDs, order or acknowledgement state.
    alarm_ids = [alarm.id for alarm in parsed.pending_alarms]
    if len(alarm_ids) != len(set(alarm_ids)):
        raise NormalizationError("Alarmes pendentes com IDs duplicados.")
    if not all(isinstance(k, str) for k in parsed.fired_hop_alarm_keys):
        raise NormalizationError("Chaves de alarme de lúpulo inválidas.")
    return parsed


def state_to_orm(raw, updated_at):
    parsed = _validate_session_payload(raw)
    item = SessionState(
        id=1,
        safety_error=parsed.safety_error,
        recipe_name=parsed.recipe_name,
        status=parsed.status,
        step_index=parsed.step_index,
        step_started_at=parsed.step_started_at,
        hold_started_at=parsed.hold_started_at,
        hold_elapsed_seconds_at_pause=parsed.hold_elapsed_seconds_at_pause,
        paused_from_status=parsed.paused_from_status,
        recipe_started_at=parsed.recipe_started_at,
        total_elapsed_seconds_frozen=parsed.total_elapsed_seconds_frozen,
        next_alarm_id=parsed.next_alarm_id,
        updated_at=updated_at,
    )
    item.fields_present = [
        SessionFieldPresence(field_name=key) for key in sorted(raw)
    ]
    item.alarms = [
        SessionAlarm(
            alarm_id=alarm.id, position=position, alarm_type=alarm.type,
            label=alarm.label, fired_at=alarm.fired_at,
        ) for position, alarm in enumerate(parsed.pending_alarms)
    ]
    item.fired_hop_keys = [
        SessionFiredHopKey(position=position, hop_key=key)
        for position, key in enumerate(parsed.fired_hop_alarm_keys)
    ]
    if parsed.control_settings is not None:
        item.control_snapshot = _control_to_orm(
            "session_snapshot:1", parsed.control_settings, 1
        )
    return item


def state_from_orm(item):
    present = {entry.field_name for entry in item.fields_present}
    values = {
        "safety_error": item.safety_error,
        "control_settings": (
            _control_from_orm(item.control_snapshot)
            if item.control_snapshot is not None else None
        ),
        "recipe_name": item.recipe_name,
        "status": item.status,
        "step_index": item.step_index,
        "step_started_at": item.step_started_at,
        "hold_started_at": item.hold_started_at,
        "hold_elapsed_seconds_at_pause": item.hold_elapsed_seconds_at_pause,
        "paused_from_status": item.paused_from_status,
        "recipe_started_at": item.recipe_started_at,
        "total_elapsed_seconds_frozen": item.total_elapsed_seconds_frozen,
        "pending_alarms": [
            {
                "id": alarm.alarm_id, "type": alarm.alarm_type,
                "label": alarm.label, "fired_at": alarm.fired_at,
            } for alarm in item.alarms
        ],
        "next_alarm_id": item.next_alarm_id,
        "fired_hop_alarm_keys": [entry.hop_key for entry in item.fired_hop_keys],
    }
    return {key: values[key] for key in present}


def persist_operational_snapshot(session, snapshot):
    if snapshot["active_recipe"] is not None:
        session.add(ActiveRecipe(
            id=1, recipe_id=snapshot["active_recipe"]["recipe_id"]
        ))
    for cal in snapshot["calibrations"]:
        session.add(SensorCalibration(**cal))
    if snapshot["state"] is not None:
        session.add(state_to_orm(
            snapshot["state"], snapshot["session_updated_at"]
        ))


def verify_operational_snapshot(session, snapshot):
    active = session.get(ActiveRecipe, 1)
    expected = snapshot["active_recipe"]
    if (None if active is None else {"id": active.id, "recipe_id": active.recipe_id}) != expected:
        raise NormalizationError("Receita ativa divergente na normalização.")

    from sqlalchemy import select
    calibrations = [
        {
            "sensor_id": entity.sensor_id, "address": entity.address,
            "offset_c": entity.offset_c, "updated_at": entity.updated_at,
        }
        for entity in session.scalars(
            select(SensorCalibration).order_by(SensorCalibration.sensor_id)
        )
    ]
    if calibrations != snapshot["calibrations"]:
        raise NormalizationError("Calibrações/ROM IDs divergentes no modelo relacional.")

    state = session.get(SessionState, 1)
    if (state is None) != (snapshot["state"] is None):
        raise NormalizationError("Estado de sessão ausente ou inesperado.")
    if state is not None:
        if state.updated_at != snapshot["session_updated_at"]:
            raise NormalizationError("Timestamp do estado de sessão divergente.")
        if state_from_orm(state) != snapshot["state"]:
            raise NormalizationError("Estado, alarmes ou snapshot PID divergente.")
    return {
        "calibrations": len(calibrations),
        "active_recipe": int(active is not None),
        "session_state": int(state is not None),
        "pending_alarms": len(state.alarms) if state else 0,
    }
