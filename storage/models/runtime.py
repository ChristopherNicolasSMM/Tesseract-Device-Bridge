"""Normalized operational snapshot, calibrations, active recipe and alarms.

These records deliberately have typed columns rather than state_json. The
snapshot of control parameters uses its own ControlProfile row so it cannot be
changed when the operator edits the next-run control profile.
"""
from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from storage.models.base import Base


class SensorCalibration(Base):
    __tablename__ = "bridge_sensor_calibrations_v2"
    sensor_id = Column(String(128), primary_key=True)
    address = Column(String(255))
    offset_c = Column(Float, nullable=False)
    updated_at = Column(Text, nullable=False)


class ActiveRecipe(Base):
    __tablename__ = "bridge_active_recipe_v2"
    id = Column(Integer, primary_key=True)
    recipe_id = Column(String(180), ForeignKey("bridge_recipes_v2.id", ondelete="SET NULL"))


class SessionState(Base):
    __tablename__ = "bridge_session_state_v2"
    id = Column(Integer, primary_key=True)
    safety_error = Column(Text)
    recipe_name = Column(String(255))
    status = Column(String(32), nullable=False)
    step_index = Column(Integer, nullable=False)
    step_started_at = Column(Float)
    hold_started_at = Column(Float)
    hold_elapsed_seconds_at_pause = Column(Float, nullable=False)
    paused_from_status = Column(String(32))
    recipe_started_at = Column(Float)
    total_elapsed_seconds_frozen = Column(Float)
    next_alarm_id = Column(Integer, nullable=False)
    updated_at = Column(Text, nullable=False)
    control_snapshot_key = Column(
        String(64), ForeignKey("bridge_control_profiles_v2.key", ondelete="SET NULL")
    )
    control_snapshot = relationship(
        "ControlProfile", cascade="all, delete-orphan", single_parent=True
    )
    fields_present = relationship(
        "SessionFieldPresence", cascade="all, delete-orphan", order_by="SessionFieldPresence.field_name"
    )
    alarms = relationship(
        "SessionAlarm", cascade="all, delete-orphan", order_by="SessionAlarm.position"
    )
    fired_hop_keys = relationship(
        "SessionFiredHopKey", cascade="all, delete-orphan", order_by="SessionFiredHopKey.position"
    )


class SessionFieldPresence(Base):
    """Preserve omitted keys in older minimal JSON session snapshots."""
    __tablename__ = "bridge_session_fields_present_v2"
    session_id = Column(
        Integer, ForeignKey("bridge_session_state_v2.id", ondelete="CASCADE"), primary_key=True
    )
    field_name = Column(String(80), primary_key=True)


class SessionAlarm(Base):
    __tablename__ = "bridge_session_alarms_v2"
    session_id = Column(
        Integer, ForeignKey("bridge_session_state_v2.id", ondelete="CASCADE"), primary_key=True
    )
    alarm_id = Column(Integer, primary_key=True)
    position = Column(Integer, nullable=False)
    alarm_type = Column(String(40), nullable=False)
    label = Column(Text, nullable=False)
    fired_at = Column(Float, nullable=False)


class SessionFiredHopKey(Base):
    __tablename__ = "bridge_session_fired_hop_keys_v2"
    session_id = Column(
        Integer, ForeignKey("bridge_session_state_v2.id", ondelete="CASCADE"), primary_key=True
    )
    position = Column(Integer, primary_key=True)
    hop_key = Column(String(128), nullable=False)
