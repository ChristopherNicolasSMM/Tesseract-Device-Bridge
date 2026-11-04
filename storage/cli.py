"""Maintenance CLI for the SQLite-backed Device Bridge."""
from __future__ import annotations

import argparse
import json
from storage import sqlite_store as store
from infra_env import load_infra_env


def main():
    load_infra_env()
    p = argparse.ArgumentParser(description="Tesseract Device Bridge - SQLite")
    p.add_argument("command", choices=("init", "status", "backup"))
    p.add_argument("--output", help="Destino do backup consistente do SQLite")
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


if __name__ == "__main__":
    main()
