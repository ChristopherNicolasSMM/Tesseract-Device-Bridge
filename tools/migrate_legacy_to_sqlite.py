#!/usr/bin/env python3
"""Import legacy files into a NEW SQLite DB. Never modifies source files.

Example:
python tools/migrate_legacy_to_sqlite.py \
    --source ../Tesseract-Device-Bridge \
    --db ./data/private/bridge.sqlite3 \
    --backup-dir ./backups
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Support invocation as python tools/... from repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from storage.legacy_import import collect, archive_source, import_snapshot


def main():
    parser = argparse.ArgumentParser(description="Migração segura YAML/JSON → SQLite")
    parser.add_argument("--source", required=True, help="Raiz da instalação antiga")
    parser.add_argument("--db", required=True, help="Caminho do NOVO banco SQLite")
    parser.add_argument("--backup-dir", help="Local privado onde salvar ZIP dos arquivos originais")
    parser.add_argument("--devices-file", default="data/public/devices.yml")
    parser.add_argument("--dry-run", action="store_true", help="Validar e inventariar, sem gravar")
    parser.add_argument(
        "--disable-invalid-remote-control", action="store_true",
        help="Com consentimento explícito, importa atuadores sem state_topic com "
             "hardware.remote_control=false; nunca habilita comandos nem altera YAML"
    )
    args = parser.parse_args()

    snapshot = collect(
        args.source, devices_file=args.devices_file,
        disable_invalid_remote_control=args.disable_invalid_remote_control,
    )
    print(json.dumps({"digest": snapshot["source_sha256"],
                      "counts": snapshot["counts"],
                      "files": sorted(snapshot["file_hashes"]),
                      "active_recipe": snapshot["active_recipe"],
                      "repairs": snapshot["repairs"]},
                     ensure_ascii=False, indent=2))
    if snapshot["repairs"]:
        print("ATENÇÃO: controle remoto DESABILITADO nos dispositivos listados em repairs. "
              "Revise esses cadastros no frontend antes de ativar operação física.")
    if args.dry_run:
        print("Pré-validação concluída. Nenhum dado foi alterado.")
        return 0
    if not args.backup_dir:
        parser.error("--backup-dir é obrigatório para importação efetiva.")
    db = Path(args.db).expanduser().resolve()
    if db.exists():
        parser.error("Destino já existe; informe um banco novo. Não sobrescreveremos instalações.")
    saved = archive_source(snapshot, args.backup_dir)
    print("Backup criado:", saved)
    target = import_snapshot(snapshot, destination=db)
    print("Migração concluída:", target)
    print("A origem permanece intacta. Configure TESSERACT_BRIDGE_DB antes de iniciar o clone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
