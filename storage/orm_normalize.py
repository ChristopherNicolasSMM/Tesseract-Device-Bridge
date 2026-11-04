"""Opt-in normalized copy migration; never switches the active runtime store.

Reads the existing SQLite legacy tables, backs up to a NEW file, runs
Alembic only on the copy, fills SQLAlchemy models and verifies equivalence.
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import select

from config import BridgeConfig
from recipe_engine.models import Recipe as DomainRecipe
from storage import sqlite_store as store
from storage.models import session_scope, BridgeSettings, Device, Recipe, ControlProfile
from storage.mappers import (
    NormalizationError,
    _config_to_orm, _config_from_orm,
    _recipe_to_orm, _recipe_from_orm,
    _control_to_orm, _control_from_orm,
)
from tesseract_bridge.infrastructure.paths import PROJECT_ROOT


def _legacy_snapshot(path):
    with store.connection(path=path) as conn:
        config, revision = store._read_config(conn)
        rows = [dict(row) for row in conn.execute(
            "SELECT id,source,editable,recipe_json,revision FROM recipes ORDER BY id"
        )]
        profiles = [dict(row) for row in conn.execute(
            "SELECT key,value_json,revision FROM settings WHERE key IN ('control','control_factory') ORDER BY key"
        )]
    parsed = BridgeConfig.from_dict(config)
    parsed.validate()
    for row in rows:
        DomainRecipe.from_dict(json.loads(row["recipe_json"])).validate(parsed)
    return config, revision, rows, profiles


def _backfill(path, snapshot):
    config, revision, recipes, profiles = snapshot
    with session_scope(path) as session:
        if session.get(BridgeSettings, 1) is not None:
            raise NormalizationError("Banco de destino já contém configurações ORM.")
        _config_to_orm(session, config, revision)
        for row in recipes:
            session.add(_recipe_to_orm(row, json.loads(row["recipe_json"])))
        for row in profiles:
            session.add(_control_to_orm(row["key"], json.loads(row["value_json"]), row["revision"]))


def _verify(path, snapshot):
    config, revision, recipes, profiles = snapshot
    with session_scope(path, readonly=True) as session:
        normalized = _config_from_orm(session)
        previous = asdict(BridgeConfig.from_dict(config))
        current = asdict(BridgeConfig.from_dict(normalized))
        if previous != current:
            raise NormalizationError("Divergência de hardware/MQTT no modelo relacional.")
        if session.get(BridgeSettings, 1).revision != revision:
            raise NormalizationError("Revisão de hardware divergente.")
        normalized_recipes = list(session.scalars(select(Recipe).order_by(Recipe.id)))
        if len(normalized_recipes) != len(recipes):
            raise NormalizationError("Número de receitas diferente.")
        for row in recipes:
            rec = session.get(Recipe, row["id"])
            if rec is None:
                raise NormalizationError("Receita ausente: " + row["id"])
            expected = asdict(DomainRecipe.from_dict(json.loads(row["recipe_json"])))
            actual = asdict(DomainRecipe.from_dict(_recipe_from_orm(rec)))
            if expected != actual or rec.revision != row["revision"]:
                raise NormalizationError("Receita divergente: " + row["id"])
        for row in profiles:
            actual = session.get(ControlProfile, row["key"])
            if actual is None or _control_from_orm(actual) != json.loads(row["value_json"]):
                raise NormalizationError("Parâmetro de controle divergente: " + row["key"])
    return {
        "devices": len(config["devices"]),
        "recipes": len(recipes),
        "control_profiles": len(profiles),
        "revision": revision,
    }


def validate_source(path):
    """Preflight all new model mappings without writing or creating files."""
    snapshot = _legacy_snapshot(Path(path).resolve())
    config, revision, recipes, profiles = snapshot

    class NoWriteSession:
        def add(self, _entity):
            # SQLAlchemy model construction and primitive validation only.
            pass

    _config_to_orm(NoWriteSession(), config, revision)
    for row in recipes:
        _recipe_to_orm(row, json.loads(row["recipe_json"]))
    for row in profiles:
        _control_to_orm(row["key"], json.loads(row["value_json"]), row["revision"])
    return snapshot


def normalize_copy(*, source, destination):
    """Create an independent and verified SQLite copy with normalized tables.

    The original remains the currently operational, JSON-backed DB until
    a separate cutover is implemented and approved.
    """
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise NormalizationError("Banco de origem não encontrado: " + str(source))
    if destination.exists():
        raise NormalizationError("Destino já existe; normalização não sobrescreve arquivos.")
    if source == destination:
        raise NormalizationError("Origem e destino não podem ser iguais.")
    snapshot = validate_source(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(destination), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    try:
        with sqlite3.connect(str(source)) as original:
            with sqlite3.connect(str(destination)) as copy:
                original.backup(copy)
        cfg = AlembicConfig(str(PROJECT_ROOT / "alembic.ini"))
        cfg.attributes["db_path"] = destination
        command.upgrade(cfg, "head")
        _backfill(destination, snapshot)
        result = _verify(destination, snapshot)
        # A copy, not the original, is modified by ORM schema and data migration.
        return {"source": str(source), "destination": str(destination), **result}
    except BaseException:
        if destination.exists():
            destination.unlink()
        raise
