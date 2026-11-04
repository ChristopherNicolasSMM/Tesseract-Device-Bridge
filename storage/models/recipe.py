"""Relational brewing recipe, vessel, step, pump and alarm records."""
from sqlalchemy import Boolean, Column, Float, ForeignKey, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from storage.models.base import Base


class Recipe(Base):
    __tablename__ = "bridge_recipes_v2"
    id = Column(String(180), primary_key=True)
    source = Column(String(16), nullable=False)
    editable = Column(Boolean, nullable=False)
    name = Column(String(255), nullable=False)
    revision = Column(Integer, nullable=False)
    vessels = relationship("RecipeVessel", back_populates="recipe", cascade="all, delete-orphan", order_by="RecipeVessel.position")
    steps = relationship("RecipeStep", back_populates="recipe", cascade="all, delete-orphan", order_by="RecipeStep.position")


class RecipeVessel(Base):
    __tablename__ = "bridge_recipe_vessels_v2"
    recipe_id = Column(String(180), ForeignKey("bridge_recipes_v2.id", ondelete="CASCADE"), primary_key=True)
    id = Column(String(128), primary_key=True)
    position = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    heater_device_id = Column(String(128), nullable=False)
    sensor_device_id = Column(String(128), nullable=False)
    kp = Column(Float, nullable=False)
    ki = Column(Float, nullable=False)
    kd = Column(Float, nullable=False)
    display_order = Column(Integer)
    recipe = relationship("Recipe", back_populates="vessels")


class RecipeStep(Base):
    __tablename__ = "bridge_recipe_steps_v2"
    id = Column(Integer, primary_key=True, autoincrement=True)
    recipe_id = Column(String(180), ForeignKey("bridge_recipes_v2.id", ondelete="CASCADE"), nullable=False, index=True)
    position = Column(Integer, nullable=False)
    vessel_id = Column(String(128), nullable=False)
    target_temp = Column(Float, nullable=False)
    hold_minutes = Column(Float, nullable=False)
    label = Column(String(255))
    recipe = relationship("Recipe", back_populates="steps")
    pumps = relationship("RecipeStepPump", cascade="all, delete-orphan", order_by="RecipeStepPump.position")
    hop_alarms = relationship("RecipeHopAlarm", cascade="all, delete-orphan", order_by="RecipeHopAlarm.position")


class RecipeStepPump(Base):
    __tablename__ = "bridge_recipe_step_pumps_v2"
    step_id = Column(Integer, ForeignKey("bridge_recipe_steps_v2.id", ondelete="CASCADE"), primary_key=True)
    position = Column(Integer, primary_key=True)
    device_id = Column(String(128), nullable=False)


class RecipeHopAlarm(Base):
    __tablename__ = "bridge_recipe_hop_alarms_v2"
    step_id = Column(Integer, ForeignKey("bridge_recipe_steps_v2.id", ondelete="CASCADE"), primary_key=True)
    position = Column(Integer, primary_key=True)
    minutes_remaining = Column(Float, nullable=False)
    label = Column(String(255), nullable=False)
