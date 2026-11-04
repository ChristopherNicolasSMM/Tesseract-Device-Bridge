"""SQLAlchemy metadata and the on-device SQLite session factory.

The Device Bridge is not a Flask-only app: GPIO workers, the migration CLI
and tests also need the database. Therefore, unlike the parent Tesseract's
Flask-SQLAlchemy integration, this uses native SQLAlchemy Session directly.
"""
from __future__ import annotations

import contextlib
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool


Base = declarative_base()


def make_engine(path):
    db_path = Path(path).expanduser().resolve()
    if not db_path.is_file():
        raise FileNotFoundError("Banco SQLite ausente: " + str(db_path))
    engine = create_engine(
        "sqlite:///" + db_path.as_posix(), future=True, poolclass=NullPool,
        connect_args={"timeout": 15},
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection, _):
        cur = dbapi_connection.cursor()
        try:
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=15000")
            cur.execute("PRAGMA synchronous=FULL")
        finally:
            cur.close()

    return engine


@contextlib.contextmanager
def session_scope(path, *, readonly=False):
    engine = make_engine(path)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    try:
        with SessionLocal() as session:
            try:
                yield session
                if readonly:
                    session.rollback()
                else:
                    session.commit()
            except BaseException:
                session.rollback()
                raise
    finally:
        engine.dispose()
