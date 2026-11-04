"""One-shot, read-only legacy YAML/JSON -> SQLite importer (Python 3.9+).

Never removes or modifies the source. Never automatically runs on bridge boot.
The SQLite destination must be empty; all import writes are one transaction.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sqlite3
import zipfile
from dataclasses import asdict
from pathlib import Path

import yaml

from config import BridgeConfig, ConfigError
from control_settings import validate_settings
from recipe_engine.models import Recipe
from recipe_engine.state import RecipeState
from temperature_calibration import validate_calibrations
from storage import sqlite_store as store


LEGACY_FILES = (
    "data/public/devices.yml",
    "data/public/receita_base.yaml",
    "data/public/receita.json",
    "data/private/receita.json",
    "data/private/control_settings.json",
    "data/private/sensor_calibration.json",
    "data/private/recipe_state.json",
    "data/active_recipe.txt",
    "data/control_defaults.json",
    "recipe.yml",
)


class LegacyImportError(RuntimeError):
    pass


def _read_json(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _needs_remote_disable(device):
    """ONLY the legacy digital/duty actuator missing its status topic.

    Never auto-repair protected heating sources or malformed actuator wiring.
    A status topic must not be invented because doing so can silently enable
    remote control or publish on an unintended MQTT topic.
    """
    if not isinstance(device, dict):
        return False
    hw = device.get("hardware")
    if not isinstance(hw, dict):
        return False
    return (
        hw.get("remote_control") is True
        and device.get("role") == "actuator"
        and (device.get("subtype") == "digital" or "window_seconds" in hw)
        and "heating_source" not in hw
        and bool(device.get("command_topic"))
        and not device.get("state_topic")
    )


def _normalize_legacy_config(original, *, disable_invalid_remote_control):
    """No source writes; opt-in safety downgrade is visible and auditable."""
    if not isinstance(original, dict):
        raise LegacyImportError("devices.yml deve conter um objeto YAML.")
    config = copy.deepcopy(original)
    invalid = [d for d in config.get("devices", []) if _needs_remote_disable(d)]
    if invalid and not disable_invalid_remote_control:
        names = ", ".join(repr(d.get("id", "<sem ID>")) for d in invalid)
        raise LegacyImportError(
            f"Dispositivos legados com hardware.remote_control=true sem state_topic: {names}. "
            "O novo schema exige state_topic para permitir ON/OFF remoto. "
            "Opções: adicione um state_topic real à CÓPIA da origem, ou use "
            "--disable-invalid-remote-control para importar esses dispositivos "
            "com remote_control=false (sem alterar os arquivos de origem). "
            "Nenhum controle remoto será habilitado automaticamente."
        )
    repairs = []
    if disable_invalid_remote_control:
        for device in invalid:
            device["hardware"]["remote_control"] = False
            repairs.append({
                "device_id": device["id"],
                "field": "hardware.remote_control",
                "source_value": True,
                "imported_value": False,
                "reason": "missing_state_topic",
            })
    try:
        validated = BridgeConfig.from_dict(config)
        validated.validate()
    except ConfigError as exc:
        raise LegacyImportError(f"Configuração de dispositivos inválida: {exc}") from exc
    return config, validated, repairs



def collect(source_dir, *, devices_file="data/public/devices.yml", disable_invalid_remote_control=False):
    """Preflight all content before touching the destination DB."""
    root = Path(source_dir).resolve()
    if not root.is_dir():
        raise LegacyImportError("Diretório de origem não existe: " + str(root))
    config_path = (root / devices_file).resolve()
    if not config_path.is_relative_to(root):
        raise LegacyImportError("O devices.yml deve estar dentro da origem.")
    if not config_path.is_file():
        raise LegacyImportError("Configuração de dispositivos ausente: " + str(config_path))
    with config_path.open("r", encoding="utf-8") as stream:
        original_config = yaml.safe_load(stream) or {}
    config, parsed, repairs = _normalize_legacy_config(
        original_config, disable_invalid_remote_control=disable_invalid_remote_control
    )

    all_paths = {p for p in LEGACY_FILES if (root / p).is_file()}
    all_paths.add(config_path.relative_to(root).as_posix())
    file_hashes = {}
    digest = hashlib.sha256()
    for rel in sorted(all_paths):
        raw = (root / rel).read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()
        file_hashes[rel] = checksum
        digest.update(rel.encode("utf-8") + b"\0" + raw + b"\0")

    recipes = []
    base_path = root / "data/public/receita_base.yaml"
    if not base_path.is_file() and (root / "recipe.yml").is_file():
        base_path = root / "recipe.yml"
    if base_path.is_file():
        raw = yaml.safe_load(base_path.read_text(encoding="utf-8")) or {}
        Recipe.from_dict(raw).validate(parsed)
        recipes.append({"id": "public:base", "source": "public", "editable": False, "recipe": raw})

    for source in ("public", "private"):
        path = root / "data" / source / "receita.json"
        entries = _read_json(path, [])
        if not isinstance(entries, list):
            raise LegacyImportError(str(path) + " deve conter uma lista de receitas.")
        seen = set()
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                raise LegacyImportError(str(path) + ": entrada de receita sem id.")
            if entry["id"] in seen:
                raise LegacyImportError(str(path) + ": ID de receita duplicado: " + entry["id"])
            seen.add(entry["id"])
            raw = entry.get("recipe")
            if not isinstance(raw, dict):
                raise LegacyImportError(str(path) + ": receita inválida: " + entry["id"])
            Recipe.from_dict(raw).validate(parsed)
            recipes.append({"id": source + ":" + entry["id"],
                            "source": source, "editable": True, "recipe": raw})
    seen_global = set()
    for entry in recipes:
        if entry["id"] in seen_global:
            raise LegacyImportError("ID global de receita duplicado: " + entry["id"])
        seen_global.add(entry["id"])

    settings = _read_json(root / "data/private/control_settings.json", store.DEFAULT_CONTROL_SETTINGS)
    validate_settings(settings)
    defaults = _read_json(root / "data/control_defaults.json", store.DEFAULT_CONTROL_SETTINGS)
    validate_settings(defaults)
    calibrations = _read_json(root / "data/private/sensor_calibration.json",
                              {"schema": 1, "sensors": {}})
    calibrations = validate_calibrations(calibrations, parsed.devices)
    state = _read_json(root / "data/private/recipe_state.json", None)
    if state is not None:
        if not isinstance(state, dict):
            raise LegacyImportError("recipe_state.json inválido.")
        # Preserve every field, but never mark an interrupted run as automatically running.
        state = asdict(RecipeState(**state))
        if state["status"] in ("ramping", "holding"):
            state["paused_from_status"] = state["status"]
            state["status"] = "paused_after_crash"

    active_path = root / "data/active_recipe.txt"
    active_id = active_path.read_text(encoding="utf-8").strip() if active_path.is_file() else None
    if active_id and active_id not in seen_global:
        raise LegacyImportError("Receita ativa aponta para ID inexistente: " + active_id)
    if not active_id and "public:base" in seen_global:
        active_id = "public:base"

    return {
        "root": root, "file_hashes": file_hashes,
        "source_sha256": digest.hexdigest(),
        "config": config, "repairs": repairs, "recipes": recipes,
        "settings": settings, "defaults": defaults,
        "calibrations": calibrations, "state": state, "active_recipe": active_id,
        "counts": {
            "devices": len(config["devices"]), "recipes": len(recipes),
            "calibrations": len(calibrations["sensors"]),
            "session_state": int(state is not None),
        },
    }


def archive_source(snapshot, backup_dir):
    """0600 ZIP with unchanged original files; never deletes originals."""
    backup_dir = Path(backup_dir).expanduser().resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / ("legacy-" + snapshot["source_sha256"][:16] + ".zip")
    if target.exists():
        raise LegacyImportError("Backup com mesmo nome já existe: " + str(target))
    fd = os.open(str(target), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        with zipfile.ZipFile(str(target), "w", zipfile.ZIP_DEFLATED) as archive:
            for rel in sorted(snapshot["file_hashes"]):
                archive.write(str(snapshot["root"] / rel), arcname=rel)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target


def import_snapshot(snapshot, *, destination):
    """Atomic initial import. Does not fall back to legacy files on failure."""
    destination = Path(destination).expanduser().resolve()
    if destination.exists():
        # Never overwrite any existing DB (even an empty DB) during migration.
        raise LegacyImportError("Banco de destino já existe. Use um caminho novo: " + str(destination))
    store.initialize(path=destination, seed=False)
    try:
        with store.connection(path=destination, writable=True) as conn:
            store._write_config(conn, snapshot["config"], action="legacy_migration")
            for recipe in snapshot["recipes"]:
                conn.execute(
                    "INSERT INTO recipes(id,source,editable,recipe_json) VALUES(?,?,?,?)",
                    (recipe["id"], recipe["source"], int(recipe["editable"]),
                     store.dumps(recipe["recipe"]))
                )
                conn.execute(
                    "INSERT INTO recipe_revisions(recipe_id,revision,recipe_json) VALUES(?,1,?)",
                    (recipe["id"], store.dumps(recipe["recipe"]))
                )
            if snapshot["active_recipe"]:
                conn.execute("INSERT INTO active_recipe(id,recipe_id) VALUES(1,?)",
                             (snapshot["active_recipe"],))
            conn.execute("INSERT INTO settings(key,value_json) VALUES('control',?)",
                         (store.dumps(snapshot["settings"]),))
            conn.execute("INSERT INTO settings(key,value_json) VALUES('control_factory',?)",
                         (store.dumps(snapshot["defaults"]),))
            for sensor_id, cal in snapshot["calibrations"]["sensors"].items():
                conn.execute(
                    "INSERT INTO sensor_calibrations(sensor_id,address,offset_c) VALUES(?,?,?)",
                    (sensor_id, cal["address"], cal["offset_c"])
                )
            if snapshot["state"] is not None:
                conn.execute("INSERT INTO session_state(id,state_json) VALUES(1,?)",
                             (store.dumps(snapshot["state"]),))
            manifest = {"file_sha256": snapshot["file_hashes"],
                        "counts": snapshot["counts"], "active_recipe": snapshot["active_recipe"],
                        "repairs": snapshot.get("repairs", [])}
            conn.execute(
                "INSERT INTO legacy_imports(source_sha256,manifest_json) VALUES(?,?)",
                (snapshot["source_sha256"], store.dumps(manifest))
            )
            conn.execute("INSERT INTO audit_events(event_type,details_json) VALUES('legacy_import',?)",
                         (store.dumps({"digest": snapshot["source_sha256"],
                                       "repairs": snapshot.get("repairs", []),
                                       **snapshot["counts"]}),))
        with store.connection(path=destination) as conn:
            assert conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0] == snapshot["counts"]["devices"]
            assert conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0] == snapshot["counts"]["recipes"]
            assert conn.execute("SELECT COUNT(*) FROM sensor_calibrations").fetchone()[0] == snapshot["counts"]["calibrations"]
            imported = store._read_config(conn)[0]
            if imported != snapshot["config"]:
                raise LegacyImportError("Configuração importada diverge da revisão aprovada.")
            for recipe in snapshot["recipes"]:
                row = conn.execute("SELECT recipe_json FROM recipes WHERE id=?", (recipe["id"],)).fetchone()
                if row is None or json.loads(row[0]) != recipe["recipe"]:
                    raise LegacyImportError("Divergência de receita importada: " + recipe["id"])
        return destination
    except BaseException:
        # A failed migration is not a valid deployment; keep no partial DB.
        if destination.exists():
            destination.unlink()
        raise
