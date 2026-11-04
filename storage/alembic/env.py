"""Independent Alembic environment for the Bridge.

Unlike the parent Tesseract, this process has no guaranteed Flask
app context: the DB factory is the native SQLAlchemy engine.
"""
from __future__ import annotations

from alembic import context

from storage.models import Base, make_engine
from tesseract_bridge.infrastructure.env import load_infra_env
from storage.sqlite_store import db_path

config = context.config
target_metadata = Base.metadata


def run_migrations_online():
    load_infra_env()
    selected = config.attributes.get("db_path") or db_path()
    engine = make_engine(selected)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
                compare_type=True,
                transaction_per_migration=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


def run_migrations_offline():
    raise RuntimeError("Migração ORM offline desativada: exige SQLite local e backup.")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
