"""Transactional, typed SQLAlchemy writing services for the simulated Bridge.

One ORM Session per operation; all changes to canonical records and their
immutable history happen in the same transaction. No JSON columns or
writes to the old SQLite schema.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from config import BridgeConfig
from control_settings import validate_settings
from recipe_engine.models import Recipe as DomainRecipe
from temperature_calibration import validate_calibrations
from storage.models import (
    session_scope, BridgeSettings, MqttSettings, PanelSettings, Device,
    Recipe, ActiveRecipe, ControlProfile, SensorCalibration, SessionState,
    ConfigurationDraft, ConfigurationRevision, RecipeRevision, AuditEvent,
)
from storage.mappers import (
    _config_from_orm, _config_to_orm, _recipe_to_orm, _recipe_from_orm,
    _control_to_orm, _control_from_orm,
)
from storage.history_mapper import _document, decode_document
from storage.session_mapper import state_to_orm, state_from_orm
from storage.repositories.orm import NormalizedRepository
from storage.migrate import StorageError
from storage.sqlite_store import dumps


def _timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _revision(session):
    head = session.get(BridgeSettings, 1)
    if head is None:
        raise StorageError("Cabeçalho de configuração ORM ausente.")
    return head.revision


def _recipe_rows(session):
    return list(session.scalars(select(Recipe).order_by(Recipe.source, Recipe.id)))


def _validate_config(session, raw):
    parsed = BridgeConfig.from_dict(raw)
    parsed.validate()
    for item in _recipe_rows(session):
        DomainRecipe.from_dict(_recipe_from_orm(item)).validate(parsed)
    for calibration in session.scalars(select(SensorCalibration)):
        sensor = next((dev for dev in parsed.devices if dev.id == calibration.sensor_id), None)
        if sensor is None or sensor.hardware.get("address") != calibration.address:
            raise StorageError(
                "Calibração/ROM ID incompatível com configuração: " + calibration.sensor_id
            )
    return parsed


def _audit(session, event_type, details, entity_id=None):
    session.add(AuditEvent(
        event_type=event_type, entity_id=entity_id,
        created_at=_timestamp(), document=_document("audit_event", details),
    ))


def _write_config(session, config, action):
    revision = _revision(session) + 1
    # Delete descendants via ORM cascade and flush first; Device.position is
    # unique, and SQLite must not see old and new rows simultaneously.
    for item in session.scalars(select(Device)):
        session.delete(item)
    session.delete(session.get(MqttSettings, 1))
    session.delete(session.get(PanelSettings, 1))
    session.delete(session.get(BridgeSettings, 1))
    session.flush()
    _config_to_orm(session, config, revision)
    session.add(ConfigurationRevision(
        revision=revision, action=action, created_at=_timestamp(),
        document=_document("configuration_revision", config),
    ))
    _audit(session, "config_revision", {"revision": revision, "action": action})
    return revision


class OrmStore(NormalizedRepository):
    """Store API used by higher layers; never accepts an unnormalized DB."""

    def load_config(self):
        return self.configuration()

    def config_revision(self):
        return self.configuration_revision()

    def apply_config(self, config, *, action="admin_apply", expected_revision=None):
        with session_scope(self.path) as session:
            current = _revision(session)
            if expected_revision is not None and expected_revision != current:
                raise StorageError("Configuração alterada por outro operador; recarregue.")
            _validate_config(session, config)
            revision = _write_config(session, config, action)
        return revision

    def save_draft(self, config):
        with session_scope(self.path) as session:
            _validate_config(session, config)
            entry = ConfigurationDraft(
                base_revision=_revision(session), status="draft",
                created_at=_timestamp(),
                document=_document("configuration_draft", config),
            )
            session.add(entry)
            session.flush()
            draft_id = entry.id
        return draft_id

    def list_drafts(self):
        with session_scope(self.path, readonly=True) as session:
            return [
                {"id": d.id, "base_revision": d.base_revision,
                 "status": d.status, "created_at": d.created_at}
                for d in session.scalars(
                    select(ConfigurationDraft).order_by(ConfigurationDraft.id.desc()).limit(30)
                )
            ]

    def load_draft(self, draft_id):
        with session_scope(self.path, readonly=True) as session:
            row = session.get(ConfigurationDraft, draft_id)
            if row is None or row.status != "draft":
                return None
            return decode_document(row.document)

    def activate_draft(self, draft_id):
        with session_scope(self.path) as session:
            draft = session.get(ConfigurationDraft, draft_id)
            if draft is None or draft.status != "draft":
                raise StorageError("Rascunho não encontrado ou já aplicado.")
            if draft.base_revision != _revision(session):
                raise StorageError("Revisão alterada desde o rascunho; reavalie.")
            payload = decode_document(draft.document)
            _validate_config(session, payload)
            revision = _write_config(session, payload, "approve_draft")
            draft.status = "applied"
        return revision

    def list_recipe_rows(self):
        with session_scope(self.path, readonly=True) as session:
            return [self._row(recipe) for recipe in _recipe_rows(session)]

    @staticmethod
    def _row(item):
        return {
            "id": item.id, "source": item.source,
            "editable": int(item.editable), "revision": item.revision,
            "recipe_json": dumps(_recipe_from_orm(item)),
        }

    def recipe_row(self, recipe_id):
        with session_scope(self.path, readonly=True) as session:
            row = session.get(Recipe, recipe_id)
            return self._row(row) if row is not None else None

    def _validated_recipe(self, session, payload):
        domain = DomainRecipe.from_dict(payload)
        domain.validate(BridgeConfig.from_dict(_config_from_orm(session)))
        return domain

    def create_recipe(self, recipe_id, source, payload):
        with session_scope(self.path) as session:
            self._validated_recipe(session, payload)
            if session.get(Recipe, recipe_id) is not None:
                raise StorageError("Receita já cadastrada.")
            if source not in ("public", "private") or not recipe_id.startswith(source + ":"):
                raise StorageError("Fonte/ID de receita incompatível.")
            row = {"id": recipe_id, "source": source, "editable": True, "revision": 1}
            session.add(_recipe_to_orm(row, payload))
            session.add(RecipeRevision(
                recipe_id=recipe_id, revision=1, created_at=_timestamp(),
                document=_document("recipe_revision", payload),
            ))
            _audit(session, "recipe_create", {}, recipe_id)

    @staticmethod
    def _update_recipe_row(session, row, payload):
        # Never delete the Recipe row: active_recipe has ON DELETE SET NULL.
        # Replacing its parent would silently clear the active selection.
        original_id = row.id
        row.name = payload["name"]
        row.revision += 1
        for item in list(row.vessels):
            row.vessels.remove(item)
        for item in list(row.steps):
            row.steps.remove(item)
        session.flush()
        fresh = _recipe_to_orm(
            {"id": original_id, "source": row.source, "editable": row.editable,
             "revision": row.revision}, payload
        )
        row.vessels = fresh.vessels
        row.steps = fresh.steps
        session.add(RecipeRevision(
            recipe_id=original_id, revision=row.revision,
            created_at=_timestamp(), document=_document("recipe_revision", payload),
        ))

    def update_recipe(self, recipe_id, payload):
        with session_scope(self.path) as session:
            self._validated_recipe(session, payload)
            row = session.get(Recipe, recipe_id)
            if row is None:
                raise StorageError("Receita não encontrada: " + recipe_id)
            if not row.editable:
                raise StorageError("Receita-base protegida; duplique-a.")
            self._update_recipe_row(session, row, payload)

    def delete_recipe(self, recipe_id):
        with session_scope(self.path) as session:
            row = session.get(Recipe, recipe_id)
            if row is None:
                raise StorageError("Receita não encontrada: " + recipe_id)
            if not row.editable:
                raise StorageError("Receita-base protegida.")
            # FK ON DELETE SET NULL handles active_recipe, historical revisions
            # deliberately do not reference this mutable recipe row.
            session.delete(row)
            session.flush()

    def replace_entities(self, source, entries):
        """Replace a catalog atomically without erasing historical revisions."""
        if source not in ("public", "private"):
            raise StorageError("Fonte de receitas inválida.")
        ids = set()
        with session_scope(self.path) as session:
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                    raise StorageError("Entrada inválida no catálogo.")
                recipe_id = source + ":" + entry["id"]
                if recipe_id in ids:
                    raise StorageError("ID duplicado no catálogo: " + recipe_id)
                ids.add(recipe_id)
                self._validated_recipe(session, entry["recipe"])
            current = list(session.scalars(
                select(Recipe).where(Recipe.source == source, Recipe.editable.is_(True))
            ))
            for item in current:
                if item.id not in ids:
                    session.delete(item)
            session.flush()
            for entry in entries:
                recipe_id = source + ":" + entry["id"]
                old = session.get(Recipe, recipe_id)
                if old is not None:
                    if not old.editable:
                        raise StorageError("Receita protegida.")
                    self._update_recipe_row(session, old, entry["recipe"])
                else:
                    session.add(_recipe_to_orm(
                        {"id": recipe_id, "source": source,
                         "editable": True, "revision": 1}, entry["recipe"],
                    ))
                    session.add(RecipeRevision(
                        recipe_id=recipe_id, revision=1, created_at=_timestamp(),
                        document=_document("recipe_revision", entry["recipe"]),
                    ))

    def get_active_recipe(self):
        return self.active_recipe()

    def set_active_recipe(self, recipe_id):
        with session_scope(self.path) as session:
            if session.get(Recipe, recipe_id) is None:
                raise StorageError("Receita não encontrada: " + str(recipe_id))
            active = session.get(ActiveRecipe, 1)
            if active is None:
                session.add(ActiveRecipe(id=1, recipe_id=recipe_id))
            else:
                active.recipe_id = recipe_id

    def load_factory_defaults(self):
        return self.control_profile("control_factory")

    def load_control(self):
        return self.control_profile("control")

    def save_control(self, payload):
        value = validate_settings(payload)
        with session_scope(self.path) as session:
            current = session.get(ControlProfile, "control")
            if current is None:
                raise StorageError("Perfil térmico ausente.")
            revision = current.revision + 1
            session.delete(current)
            session.flush()
            session.add(_control_to_orm("control", value, revision))

    def load_calibrations(self):
        return self.calibrations()

    def save_calibrations(self, payload):
        with session_scope(self.path) as session:
            parsed = BridgeConfig.from_dict(_config_from_orm(session))
            value = validate_calibrations(payload, parsed.devices)
            for existing in session.scalars(select(SensorCalibration)):
                session.delete(existing)
            session.flush()
            for sensor_id, row in value["sensors"].items():
                session.add(SensorCalibration(
                    sensor_id=sensor_id, address=row["address"],
                    offset_c=row["offset_c"], updated_at=_timestamp(),
                ))

    def load_session_state(self):
        return self.session_state()

    def save_session_state(self, payload):
        with session_scope(self.path) as session:
            current = session.get(SessionState, 1)
            if current is not None:
                session.delete(current)
                session.flush()
            session.add(state_to_orm(payload, _timestamp()))

    def audit_events(self, limit=100):
        with session_scope(self.path, readonly=True) as session:
            return [
                {"id": row.id, "event_type": row.event_type,
                 "entity_id": row.entity_id, "details_json": dumps(decode_document(row.document)),
                 "created_at": row.created_at}
                for row in session.scalars(
                    select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
                )
            ]
