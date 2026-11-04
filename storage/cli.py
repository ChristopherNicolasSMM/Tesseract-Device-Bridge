"""Maintenance CLI for the SQLite-backed Device Bridge."""
from __future__ import annotations

import argparse
import json
from storage import sqlite_store as store
from tesseract_bridge.infrastructure.env import load_infra_env


def main():
    load_infra_env()
    p = argparse.ArgumentParser(description="Tesseract Device Bridge - SQLite")
    p.add_argument("command", choices=("init", "status", "backup", "normalize"))
    p.add_argument("--output", help="Destino do backup ou NOVO banco normalizado")
    p.add_argument("--dry-run", action="store_true", help="Somente verificar a origem JSON, sem escrever")
    args = p.parse_args()
    if args.command == "init":
        print("Banco inicializado (simulado até configurar hardware):", store.initialize())
    elif args.command == "status":
        from storage.launch_config import load_runtime_config
        config = store.load_config()
        effective = load_runtime_config()
        print(json.dumps({"db": str(store.db_path()),
                          "backend_saved": config["backend"],
                          "backend_runtime": effective.backend,
                          "mqtt_runtime_enabled": effective.mqtt.enabled,
                          "panel_runtime_host": effective.panel.host,
                          "panel_runtime_port": effective.panel.port,
                          "devices": len(config["devices"]),
                          "revision": store.config_revision(),
                          "recipes": len(store.list_recipe_rows())}, ensure_ascii=False, indent=2))
    elif args.command == "backup":
        if not args.output:
            p.error("backup exige --output")
        print("Backup:", store.backup(args.output))
    elif args.command == "normalize":
        from storage.orm_normalize import normalize_copy, validate_source
        original = store.db_path()
        if args.dry_run:
            config, revision, recipes, profiles = validate_source(original)
            print(json.dumps({"source": str(original), "devices": len(config["devices"]),
                              "recipes": len(recipes), "control_profiles": len(profiles),
                              "revision": revision, "dry_run": True}, ensure_ascii=False, indent=2))
        else:
            if not args.output:
                p.error("normalize exige --output para gerar um NOVO arquivo (nunca sobrescreve).")
            print(json.dumps(normalize_copy(source=original, destination=args.output),
                             ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
