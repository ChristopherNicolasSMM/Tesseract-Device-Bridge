"""Maintenance CLI for the SQLite-backed Device Bridge."""
from __future__ import annotations

import argparse
import json
from storage import store_router as store
from tesseract_bridge.infrastructure.env import load_infra_env


def main():
    load_infra_env()
    p = argparse.ArgumentParser(description="Tesseract Device Bridge - SQLite")
    p.add_argument("command", choices=("init", "status", "backup", "normalize", "orm-audit"))
    p.add_argument("--output", help="Destino do backup ou NOVO banco normalizado")
    p.add_argument("--dry-run", action="store_true", help="Somente verificar a origem JSON, sem escrever")
    p.add_argument("--candidate", help="Caminho da cópia normalizada para auditoria ORM")
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
                          "storage_mode": store.storage_mode(),
                          "runtime_cutover_enabled": store.storage_mode() == "orm",
                          "revision": store.config_revision(),
                          "recipes": len(store.list_recipe_rows())}, ensure_ascii=False, indent=2))
    elif args.command == "backup":
        if not args.output:
            p.error("backup exige --output")
        print("Backup:", store.backup(args.output))
    elif args.command == "orm-audit":
        if store.storage_mode() != "legacy":
            p.error("orm-audit exige STORAGE_MODE=legacy e DB de origem.")
        from storage.orm_audit import audit_copy
        if not args.candidate:
            p.error("orm-audit exige --candidate, sem alterar o .env")
        print(json.dumps(audit_copy(source=store.db_path(), candidate=args.candidate),
                         ensure_ascii=False, indent=2))
    elif args.command == "normalize":
        if store.storage_mode() != "legacy":
            p.error("normalize exige STORAGE_MODE=legacy e DB de origem.")
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
