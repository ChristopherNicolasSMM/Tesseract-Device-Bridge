"""Typed SQLAlchemy models for the hardware registry and infrastructure."""
from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from storage.models.base import Base


class BridgeSettings(Base):
    __tablename__ = "bridge_settings_v2"
    id = Column(Integer, primary_key=True)
    backend = Column(String(16), nullable=False)
    revision = Column(Integer, nullable=False)


class MqttSettings(Base):
    __tablename__ = "mqtt_settings_v2"
    id = Column(Integer, primary_key=True)
    enabled = Column(Boolean, nullable=False)
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    username = Column(String(255))
    password = Column(Text)
    client_id = Column(String(255), nullable=False)
    topic_prefix = Column(String(255), nullable=False)
    reconnect_interval_seconds = Column(Integer, nullable=False)


class PanelSettings(Base):
    __tablename__ = "panel_settings_v2"
    id = Column(Integer, primary_key=True)
    enabled = Column(Boolean, nullable=False)
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)


class Device(Base):
    __tablename__ = "bridge_devices_v2"
    id = Column(String(128), primary_key=True)
    position = Column(Integer, nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)
    subtype = Column(String(30))
    unit = Column(String(30))
    state_topic = Column(String(512))
    command_topic = Column(String(512))
    is_risk = Column(Boolean, nullable=False, default=False)
    is_risk_present = Column(Boolean, nullable=False, default=False)
    simulated_present = Column(Boolean, nullable=False, default=False)
    limits_present = Column(Boolean, nullable=False, default=False)
    failsafe_kind = Column(String(16))
    failsafe_text = Column(Text)
    failsafe_timeout_seconds = Column(Integer)
    pin = Column(Integer, nullable=False)
    driver = Column(String(50))
    address = Column(String(255))
    window_seconds = Column(Float)
    active_high = Column(Boolean)
    remote_control = Column(Boolean)
    external_control_policy = Column(String(30))
    properties = relationship("DeviceProperty", cascade="all, delete-orphan", back_populates="device")
    heating_source = relationship("DeviceHeatingSource", cascade="all, delete-orphan", uselist=False, back_populates="device")


class DeviceProperty(Base):
    """Typed simple extension values, never an opaque JSON payload.

    Only flat primitive values are supported; unexpected nested input fails
    the preflight instead of silently destroying an unknown hardware field.
    """
    __tablename__ = "bridge_device_properties_v2"
    device_id = Column(String(128), ForeignKey("bridge_devices_v2.id", ondelete="CASCADE"), primary_key=True)
    namespace = Column(String(30), primary_key=True)
    key = Column(String(128), primary_key=True)
    value_kind = Column(String(16), nullable=False)
    value_text = Column(Text)
    device = relationship("Device", back_populates="properties")


class DeviceHeatingSource(Base):
    __tablename__ = "bridge_device_heat_sources_v2"
    device_id = Column(String(128), ForeignKey("bridge_devices_v2.id", ondelete="CASCADE"), primary_key=True)
    participation = Column(String(30), nullable=False)
    temperature_sensor = Column(String(128), nullable=False)
    controller_device = Column(String(128))
    external_flame_cutoff = Column(Boolean, nullable=False)
    device = relationship("Device", back_populates="heating_source")
