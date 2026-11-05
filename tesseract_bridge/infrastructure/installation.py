"""Read-only publication gate. No setup, Flask, GPIO or ORM imports."""
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from .env import flag
from .paths import PROJECT_ROOT

RECEIPT = 'data/private/installation.json'


def read_receipt(root):
    path = Path(root) / RECEIPT
    if path.is_symlink():
        raise RuntimeError('Linked installation receipt rejected.')
    return json.loads(path.read_text(encoding='utf-8'))


def check_runtime(db, *, root=None, simulated=None):
    root = Path(root) if root is not None else PROJECT_ROOT
    simulated = flag('TESSERACT_BRIDGE_SIMULATION_ONLY', False) if simulated is None else simulated
    selected = Path(db).resolve()
    managed = os.environ.get('TESSERACT_BRIDGE_INSTALL_ID', '')
    receipt_path = root / RECEIPT
    # Preserve explicitly simulated historical ORM sandboxes.
    if not managed and simulated and selected != (root / 'data/private/bridge.sqlite3').resolve():
        return
    if not receipt_path.is_file():
        if simulated and not managed:
            return
        raise RuntimeError('ORM exige conclusão válida do setup; use SIMULATION_ONLY=1 até concluir.')
    receipt = read_receipt(root)
    if receipt.get('version') != 1 or receipt.get('status') not in ('ready_simulated', 'ready_operational', 'needs_review'):
        raise RuntimeError('Publicação incompleta. Retome ou recupere o setup antes de iniciar.')
    if selected != (root / receipt['database']).resolve():
        raise RuntimeError('Banco selecionado não pertence à instalação publicada.')
    if managed and managed != receipt.get('id'):
        raise RuntimeError('Configuração e instalação pertencem a tentativas diferentes.')
    if not simulated and receipt['status'] != 'ready_operational':
        raise RuntimeError('Instalação não aprovada para modo configurado; mantenha SIMULATION_ONLY=1.')
    with closing(sqlite3.connect(selected.as_uri() + '?mode=ro', uri=True)) as conn:
        identity = conn.execute('PRAGMA application_id').fetchone()[0]
    if identity != receipt.get('database_identity'):
        raise RuntimeError('Identidade do banco difere da instalação publicada.')


def check_boot_publication(root=None):
    root = Path(root) if root is not None else PROJECT_ROOT
    path = root / RECEIPT
    if path.exists() or path.is_symlink():
        receipt = read_receipt(root)
        if receipt.get('status') not in ('ready_simulated', 'ready_operational', 'needs_review'):
            raise RuntimeError('Publicação incompleta. Retome ou recupere o setup antes de iniciar.')
        if os.environ.get('TESSERACT_BRIDGE_STORAGE_MODE', 'legacy').strip().lower() != 'orm':
            raise RuntimeError('Instalação publicada pelo setup exige backend ORM.')
        selected = Path(os.environ.get('TESSERACT_BRIDGE_DB', str(root / receipt['database'])))
        if not selected.is_absolute():
            selected = root / selected
        check_runtime(selected, root=root)
