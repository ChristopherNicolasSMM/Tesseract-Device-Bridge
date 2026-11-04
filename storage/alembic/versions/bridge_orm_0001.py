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
    for table in Base.metadata.sorted_tables:
        table.create(bind=bind, checkfirst=False)


def downgrade():
    raise RuntimeError("Downgrade bloqueado: preserve os dados e restaure backup explícito.")
