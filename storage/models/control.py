"""Relational control settings and calibration profiles."""
from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from storage.models.base import Base


class ControlProfile(Base):
    __tablename__ = "bridge_control_profiles_v2"
    key = Column(String(64), primary_key=True)
    revision = Column(Integer, nullable=False, default=1)
    alert_above = Column(Float, nullable=False)
    alert_clear = Column(Float, nullable=False)
    freeze_hold_on_alert = Column(Boolean, nullable=False)
    boil_temperature = Column(Float, nullable=False)
    boil_power = Column(Float, nullable=False)
    curve = relationship("ControlCurvePoint", cascade="all, delete-orphan", order_by="ControlCurvePoint.position")
    vessel_profiles = relationship("ControlVesselProfile", cascade="all, delete-orphan")


class ControlCurvePoint(Base):
    __tablename__ = "bridge_control_curve_v2"
    profile_key = Column(String(64), ForeignKey("bridge_control_profiles_v2.key", ondelete="CASCADE"), primary_key=True)
    position = Column(Integer, primary_key=True)
    delta = Column(Float, nullable=False)
    power = Column(Float, nullable=False)


class ControlVesselProfile(Base):
    __tablename__ = "bridge_control_vessel_profiles_v2"
    profile_key = Column(String(64), ForeignKey("bridge_control_profiles_v2.key", ondelete="CASCADE"), primary_key=True)
    vessel_id = Column(String(128), primary_key=True)
    profile = Column(String(16), nullable=False)
