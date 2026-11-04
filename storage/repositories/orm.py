"""Typed SQLAlchemy repositories, isolated from GPIO/Flask request handling.

The live runtime still uses sqlite_store. Until the cutover is complete,
write operations here are for an explicitly selected NORMALIZED COPY only.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from config import BridgeConfig
from control_settings import validate_settings
from recipe_engine.models import Recipe as DomainRecipe
from storage.mappers import (
    NormalizationError,
    _config_from_orm,
    _recipe_from_orm,
    _control_from_orm,
    _control_to_orm,
)
from storage.models import (
    BridgeSettings,
    ControlProfile,
    Recipe,
    ActiveRecipe,
    SensorCalibration,
    SessionState,
    session_scope,
)
from storage.session_mapper import state_from_orm
from storage.models import (
    ConfigurationRevision, ConfigurationDraft, RecipeRevision,
    AuditEvent, LegacyImport, LegacySchemaMigration,
)


class RepositoryError(RuntimeError):
    """Invalid or incomplete normalized database."""


class NormalizedRepository:
    """Access models through short-lived sessions, not a process-global Session."""

    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        if not self.path.is_file():
            raise RepositoryError("Banco normalizado não encontrado: " + str(self.path))
        self._assert_initialized()

    def _assert_initialized(self):
        try:
            with session_scope(self.path, readonly=True) as session:
                if session.get(BridgeSettings, 1) is None:
                    raise RepositoryError("Modelos relacionais não inicializados. Execute normalize.")
                version = session.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one_or_none()
                if version != "bridge_orm_0003":
                    raise RepositoryError(
                        "Cópia ORM de revisão antiga; normalize uma NOVA cópia "
                        "com o código atualizado antes de utilizá-la."
                    )
        except SQLAlchemyError as exc:
            raise RepositoryError(
                "Banco sem tabelas ORM. Normalize uma cópia antes de utilizar os repositórios."
            ) from exc

    def configuration(self):
        with session_scope(self.path, readonly=True) as session:
            result = _config_from_orm(session)
            BridgeConfig.from_dict(result).validate()
            return result

    def configuration_revision(self):
        with session_scope(self.path, readonly=True) as session:
            header = session.get(BridgeSettings, 1)
            if header is None:
                raise RepositoryError("Configuração ORM não encontrada.")
            return header.revision

    def list_recipes(self):
        with session_scope(self.path, readonly=True) as session:
            return [
                {
                    "id": entity.id, "source": entity.source,
                    "editable": bool(entity.editable),
                    "revision": entity.revision,
                    "recipe": _recipe_from_orm(entity),
                }
                for entity in session.scalars(select(Recipe).order_by(Recipe.source, Recipe.id))
            ]

    def recipe(self, recipe_id):
        with session_scope(self.path, readonly=True) as session:
            entity = session.get(Recipe, recipe_id)
            if entity is None:
                return None
            return {
                "id": entity.id, "source": entity.source,
                "editable": bool(entity.editable), "revision": entity.revision,
                "recipe": _recipe_from_orm(entity),
            }

    def active_recipe(self):
        with session_scope(self.path, readonly=True) as session:
            row = session.get(ActiveRecipe, 1)
            return row.recipe_id if row is not None else None

    def calibrations(self):
        with session_scope(self.path, readonly=True) as session:
            return {"schema": 1, "sensors": {
                row.sensor_id: {
                    "address": row.address,
                    "offset_c": row.offset_c,
                } for row in session.scalars(
                    select(SensorCalibration).order_by(SensorCalibration.sensor_id)
                )
            }}

    def session_state(self):
        """Read-only execution snapshot, never an automatic hardware resume."""
        with session_scope(self.path, readonly=True) as session:
            row = session.get(SessionState, 1)
            return state_from_orm(row) if row is not None else None

    def history_counts(self):
        """Counts only; no historical payloads, tokens or credentials decoded."""
        tables = {
            "configuration_revisions": ConfigurationRevision,
            "configuration_drafts": ConfigurationDraft,
            "recipe_revisions": RecipeRevision,
            "audit_events": AuditEvent,
            "legacy_imports": LegacyImport,
            "schema_migrations": LegacySchemaMigration,
        }
        with session_scope(self.path, readonly=True) as session:
            return {
                name: session.scalar(select(func.count()).select_from(model))
                for name, model in tables.items()
            }

    def control_profile(self, key="control"):
        with session_scope(self.path, readonly=True) as session:
            entity = session.get(ControlProfile, key)
            if entity is None:
                raise RepositoryError("Perfil térmico ORM não encontrado: " + key)
            return _control_from_orm(entity)

    def control_revision(self, key="control"):
        with session_scope(self.path, readonly=True) as session:
            entity = session.get(ControlProfile, key)
            if entity is None:
                raise RepositoryError("Perfil térmico ORM não encontrado: " + key)
            return entity.revision

    def save_control_profile(self, payload, *, expected_revision, key="control"):
        """A standalone transactional write on a test copy, never legacy JSON.

        This method is intentionally not wired to the current runtime: no dual
        writes, no accidental drift between the two persistence schemas.
        """
        if key != "control":
            raise RepositoryError("Somente o perfil operacional pode ser editado.")
        with session_scope(self.path) as session:
            previous = session.get(ControlProfile, key)
            if previous is None:
                raise RepositoryError("Perfil ORM ausente.")
            if previous.revision != expected_revision:
                raise RepositoryError(
                    "Revisão alterada por outro operador. Recarregue antes de salvar."
                )
            factory = session.get(ControlProfile, "control_factory")
            if factory is None:
                raise RepositoryError("Padrões de fábrica ausentes na cópia ORM.")
            value = validate_settings(
                payload, defaults=_control_from_orm(factory)
            )
            next_revision = previous.revision + 1
            session.delete(previous)
            session.flush()
            session.add(_control_to_orm(key, value, next_revision))
        return next_revision
