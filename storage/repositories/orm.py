"""Typed SQLAlchemy repositories, isolated from GPIO/Flask request handling.

The live runtime still uses sqlite_store. Until the cutover is complete,
write operations here are for an explicitly selected NORMALIZED COPY only.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
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
    session_scope,
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
        value = validate_settings(payload)
        with session_scope(self.path) as session:
            previous = session.get(ControlProfile, key)
            if previous is None:
                raise RepositoryError("Perfil ORM ausente.")
            if previous.revision != expected_revision:
                raise RepositoryError(
                    "Revisão alterada por outro operador. Recarregue antes de salvar."
                )
            next_revision = previous.revision + 1
            session.delete(previous)
            session.flush()
            session.add(_control_to_orm(key, value, next_revision))
        return next_revision
