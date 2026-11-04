"""Normalize active recipe, ROM calibration and crash-safe session snapshot.

Revision ID: bridge_orm_0002
Revises: bridge_orm_0001
"""
from __future__ import annotations

from alembic import op
from storage.models import Base

revision = "bridge_orm_0002"
down_revision = "bridge_orm_0001"
branch_labels = None
depends_on = None


def upgrade():
    tables = {
        "bridge_sensor_calibrations_v2", "bridge_active_recipe_v2",
        "bridge_session_state_v2", "bridge_session_fields_present_v2",
        "bridge_session_alarms_v2", "bridge_session_fired_hop_keys_v2",
    }
    assert tables <= set(Base.metadata.tables)
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        if table.name in tables:
            table.create(bind=bind, checkfirst=False)


def downgrade():
    raise RuntimeError("Downgrade bloqueado; restaure uma cópia anterior explicitamente.")
