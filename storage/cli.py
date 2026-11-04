"""Maintenance CLI for the SQLite-backed Device Bridge."""
from __future__ import annotations

import argparse
import json
from storage import sqlite_store as store


def main():
    p = argparse.ArgumentParser(description="Tesseract Device Bridge - SQLite")
    p.add_argument("command", choices=("init", "status", "backup"))
    p.add_argument("--output", help="Destino do backup consistente do SQLite")
    args = p.parse_args()
    if args.command == "init":
        print("Banco inicializado (simulado até configurar hardware):", store.initialize())
    elif args.command == "status":
        config = store.load_config()
        print(json.dumps({"db": str(store.db_path()), "backend": config["backend"],
                          "devices": len(config["devices"]),
                          "revision": store.config_revision(),
                          "recipes": len(store.list_recipe_rows())}, ensure_ascii=False, indent=2))
    elif args.command == "backup":
        if not args.output:
            p.error("backup exige --output")
        print("Backup:", store.backup(args.output))


if __name__ == "__main__":
    main()
