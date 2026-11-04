"""Administrative SQLite endpoints.

No hardware manipulation is performed here. Changes are drafted, validated,
and approved for a subsequent, explicitly supervised Bridge restart.
"""
from __future__ import annotations

import os
import secrets
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_file

from config import BridgeConfig, ConfigError
from recipe_engine.models import Recipe, RecipeError
from storage import store_router as store
from storage.migrate import StorageError

bp = Blueprint("admin_sqlite", __name__, url_prefix="/api/admin")


def _authenticated():
    expected = os.environ.get("TESSERACT_BRIDGE_ADMIN_TOKEN", "")
    received = request.headers.get("X-Bridge-Admin-Token", "")
    return len(expected) >= 16 and bool(received) and secrets.compare_digest(expected, received)


@bp.before_request
def require_admin():
    if not os.environ.get("TESSERACT_BRIDGE_ADMIN_TOKEN"):
        return jsonify(error="Administração desativada: defina TESSERACT_BRIDGE_ADMIN_TOKEN (mínimo 16 caracteres)."), 503
    if not _authenticated():
        return jsonify(error="Token de administração inválido."), 401


def _not_running():
    engine = current_app.config.get("RECIPE_ENGINE")
    if engine is not None and engine.state.status in ("ramping", "holding", "paused_manual", "paused_after_crash"):
        raise StorageError("Finalize/cancele a sessão e isole as saídas antes de alterar hardware.")
    state = store.load_session_state() or {}
    if state.get("status") in ("ramping", "holding", "paused_manual"):
        raise StorageError("Estado de sessão ativa armazenado no banco; não é seguro aplicar configuração.")
    runtime = current_app.config.get("DEVICE_RUNTIME")
    if runtime is not None and runtime.emergency_reason:
        raise StorageError("Bridge em emergência; alterações de configuração exigem diagnóstico e reinício.")


def _validated_config(payload):
    if not isinstance(payload, dict):
        raise ValueError("Configuração precisa ser um objeto JSON.")
    current = store.load_config()
    # Never expose the existing MQTT secret to the browser.
    if "mqtt" in payload and isinstance(payload["mqtt"], dict) and payload["mqtt"].get("password") is None:
        payload["mqtt"]["password"] = current["mqtt"].get("password")
    cfg = BridgeConfig.from_dict(payload)
    cfg.validate()
    for row in store.list_recipe_rows():
        try:
            Recipe.from_dict(__import__("json").loads(row["recipe_json"])).validate(cfg)
        except (RecipeError, ValueError, TypeError) as exc:
            raise ValueError(f"Dispositivo incompatível com receita {row['id']}: {exc}") from exc
    for sensor_id, entry in store.load_calibrations()["sensors"].items():
        sensor = next((d for d in cfg.devices if d.id == sensor_id), None)
        if sensor is None or sensor.hardware.get("address") != entry["address"]:
            raise ValueError(f"Calibração de {sensor_id} inválida para esta revisão. Revise o sensor primeiro.")
    return payload


@bp.get("/config")
def get_config():
    config = store.load_config()
    has_password = bool(config.get("mqtt", {}).get("password"))
    config["mqtt"]["password"] = None
    return jsonify(config=config, revision=store.config_revision(),
                   mqtt_password_set=has_password,
                   note="Alterações só chegam ao runtime após aprovação e reinício seguro.")


@bp.get("/drafts")
def get_drafts():
    return jsonify(drafts=store.list_drafts())


@bp.post("/drafts")
def create_draft():
    try:
        _not_running()
        payload = request.get_json(silent=True)
        config = _validated_config(payload)
        draft_id = store.save_draft(config)
        return jsonify(id=draft_id, restart_required=True), 201
    except (ValueError, TypeError, KeyError, ConfigError, StorageError) as exc:
        return jsonify(error=str(exc)), 409


@bp.post("/drafts/<int:draft_id>/activate")
def activate_draft(draft_id):
    try:
        _not_running()
        payload = store.load_draft(draft_id)
        if payload is None:
            raise StorageError("Rascunho inexistente.")
        _validated_config(payload)
        revision = store.activate_draft(draft_id)
        return jsonify(revision=revision, restart_required=True,
                       note="Configuração aprovada no SQLite. Encerre o processo e reinicie apenas em condição segura.")
    except (ValueError, TypeError, ConfigError, StorageError) as exc:
        return jsonify(error=str(exc)), 409


@bp.get("/audit")
def get_audit():
    return jsonify(events=store.audit_events(100))


@bp.get("/storage")
def storage_status():
    config = store.load_config()
    return jsonify(backend=config["backend"], devices=len(config["devices"]),
                   recipes=len(store.list_recipe_rows()),
                   revision=store.config_revision(),
                   database=str(store.db_path()), mode=store.storage_mode())


@bp.post("/backup")
def create_backup():
    try:
        _not_running()
        backup_dir = store.db_path().parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        filename = datetime.now().strftime("bridge-%Y%m%d-%H%M%S") + "-" + secrets.token_hex(4) + ".sqlite3"
        file_path = backup_dir / filename
        store.backup(file_path)
        return jsonify(file=filename, note="Cópia consistente criada. Guarde uma cópia externa.")
    except (StorageError, OSError, sqlite3.Error) as exc:
        return jsonify(error=str(exc)), 409


@bp.get("/backup/<filename>")
def download_backup(filename):
    # Strict filename and resolved directory prevent traversal.
    if not filename.startswith("bridge-") or not filename.endswith(".sqlite3") or "/" in filename or "\\" in filename:
        return jsonify(error="Nome inválido"), 400
    root = (store.db_path().parent / "backups").resolve()
    target = (root / filename).resolve()
    if target.parent != root or not target.is_file():
        return jsonify(error="Backup não encontrado"), 404
    return send_file(str(target), as_attachment=True, download_name=filename)
