"""Schema relational inicial, sobre cópia do banco legado SQLite.

Revision ID: bridge_orm_0001
Revises:
"""
from __future__ import annotations

from alembic import op

from storage.models import Base

revision = "bridge_orm_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # All new entities use the _v2 suffix during parallel validation so the
    # current JSON-backed runtime remains untouched until cutover.
    bind = op.get_bind()
    # Keep this historical revision stable. Do not dynamically create future
    # Base.metadata tables when replaying the first migration on a fresh DB.
    initial_tables = {
        "bridge_settings_v2", "mqtt_settings_v2", "panel_settings_v2",
        "bridge_devices_v2", "bridge_device_properties_v2",
        "bridge_device_heat_sources_v2", "bridge_recipes_v2",
        "bridge_recipe_vessels_v2", "bridge_recipe_steps_v2",
        "bridge_recipe_step_pumps_v2", "bridge_recipe_hop_alarms_v2",
        "bridge_control_profiles_v2", "bridge_control_curve_v2",
        "bridge_control_vessel_profiles_v2",
    }
    assert initial_tables <= set(Base.metadata.tables)
    for table in Base.metadata.sorted_tables:
        if table.name in initial_tables:
            table.create(bind=bind, checkfirst=False)


def downgrade():
    raise RuntimeError("Downgrade bloqueado: preserve os dados e restaure backup explícito.")
