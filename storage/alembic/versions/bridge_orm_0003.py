"""Normalize historical revisions, drafts, audit events and import manifests.

Revision ID: bridge_orm_0003
Revises: bridge_orm_0002
"""
from __future__ import annotations

from alembic import op
from storage.models import Base

revision = "bridge_orm_0003"
down_revision = "bridge_orm_0002"
branch_labels = None
depends_on = None


def upgrade():
    # Migrations must remain immutable when later models are introduced.
    tables = {
        "bridge_history_documents_v2",
        "bridge_history_nodes_v2",
        "bridge_configuration_revisions_v2",
        "bridge_configuration_drafts_v2",
        "bridge_recipe_revisions_v2",
        "bridge_audit_events_v2",
        "bridge_legacy_imports_v2",
        "bridge_legacy_schema_migrations_v2",
    }
    assert tables <= set(Base.metadata.tables)
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        if table.name in tables:
            table.create(bind=bind, checkfirst=False)


def downgrade():
    raise RuntimeError(
        "Downgrade destrutivo bloqueado. Restaure um backup verificado."
    )
