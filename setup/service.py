"""Single managed-systemd adapter, invoked by audited tools scripts, never via web sudo."""
import argparse
import getpass
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .state import SetupError


def compatible():
    return platform.system() == 'Linux' and Path('/run/systemd/system').is_dir() and bool(shutil.which('systemctl'))


def unit_quote(value, *, executable=False):
    if any(c in value for c in ('\n', '\r', '\x00')):
        raise SetupError('Invalid systemd path.')
    escaped = value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    if executable:
        escaped = escaped.replace('$', '$$')
    return '"' + escaped + '"'


def generate(state, user=None):
    from .publication import load_publication
    if not compatible():
        raise SetupError('Automatic service installation requires Linux with active systemd.')
    receipt, _ = load_publication(state)
    if receipt['status'] not in ('ready_simulated', 'ready_operational'):
        raise SetupError('Service requires a completed installation without review blockers.')
    user = user or getpass.getuser()
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*[$]?', user) or user == 'root':
        raise SetupError('Choose a valid non-root service user.')
    import pwd
    account = pwd.getpwnam(user)
    if account.pw_uid == 0 or account.pw_uid != os.getuid():
        raise SetupError('Run setup as the intended non-root service user so private data stays accessible.')
    group = __import__('grp').getgrgid(account.pw_gid).gr_name
    directory = state.directory / 'services'
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.is_symlink():
        raise SetupError('Linked service directory rejected.')
    name = 'tesseract-bridge-' + receipt['id'][:12] + '.service'
    target = directory / name
    text = ('# Managed by Tesseract setup; install-id=' + receipt['id'] + '\n'
        '[Unit]\nDescription=Tesseract Device Bridge\nAfter=network-online.target\n'
        'Wants=network-online.target\nStartLimitIntervalSec=60\nStartLimitBurst=5\n'
        '[Service]\nType=simple\nUser=' + user + '\nGroup=' + group + '\n'
        'WorkingDirectory=' + unit_quote(str(state.root)) + '\n'
        'ExecStart=' + unit_quote(sys.executable, executable=True) + ' ' + unit_quote(str(state.root / 'run_bridge.py'), executable=True) + '\n'
        'Environment=PYTHONUNBUFFERED=1\nRestart=on-failure\nRestartSec=5\n'
        'TimeoutStopSec=15\nUMask=0077\nStandardOutput=journal\nStandardError=journal\n'
        '[Install]\nWantedBy=multi-user.target\n')
    if target.exists() or target.is_symlink():
        if target.is_symlink() or target.read_text(encoding='utf-8') != text:
            raise SetupError('Service definition already exists with different content.')
    else:
        fd = os.open(str(target), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
    return target


def run(action, unit, root):
    from .publication import digest
    if not compatible() or os.geteuid() != 0:
        raise SetupError('Use the explicit sudo tools command on a systemd host.')
    unit = Path(unit).resolve()
    root = Path(root).resolve()
    expected_dir = root / 'data/private/setup/services'
    if unit.parent != expected_dir or not re.fullmatch(r'tesseract-bridge-[0-9a-f]{12}\.service', unit.name):
        raise SetupError('Not a setup-managed service definition.')
    content = unit.read_text(encoding='utf-8')
    receipt = json.loads((root / 'data/private/installation.json').read_text(encoding='utf-8'))
    if (receipt['status'] not in ('ready_simulated', 'ready_operational')
            or not content.startswith('# Managed by Tesseract setup; install-id=' + receipt['id'] + '\n')
            or unit.name != 'tesseract-bridge-' + receipt['id'][:12] + '.service'):
        raise SetupError('Service does not belong to the completed installation.')
    destination = Path('/etc/systemd/system') / unit.name
    registry = expected_dir / (unit.name + '.installed.json')
    if action == 'install':
        subprocess.run(['systemd-analyze', 'verify', str(unit)], check=True)
        if destination.exists() or destination.is_symlink():
            raise SetupError('Existing systemd unit will not be overwritten.')
        from .publication import atomic_json
        # Record ownership before creating the unit, so an interruption can be diagnosed.
        atomic_json(registry, dict(id=receipt['id'], sha256=digest(unit)))
        created_inode = None
        try:
            fd = os.open(str(destination), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            created_inode = os.fstat(fd).st_ino
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            subprocess.run(['systemctl', 'daemon-reload'], check=True)
        except BaseException:
            # Roll back only the inode created by this attempt, never another unit.
            if (created_inode is not None and destination.exists() and not destination.is_symlink()
                    and destination.stat().st_ino == created_inode):
                destination.unlink()
            registry.unlink(missing_ok=True)
            raise
        return
    if (destination.is_symlink() or not destination.is_file() or not registry.is_file()
            or registry.is_symlink()):
        raise SetupError('No owned service installation found.')
    saved = json.loads(registry.read_text(encoding='utf-8'))
    if saved['id'] != receipt['id'] or saved['sha256'] != digest(destination) or digest(unit) != saved['sha256']:
        raise SetupError('Installed service differs; refusing to change or remove it.')
    if action == 'enable':
        subprocess.run(['systemctl', 'enable', unit.name], check=True)
    elif action == 'start':
        from tesseract_bridge.infrastructure.installation import check_runtime
        env = __import__('dotenv').dotenv_values(root / '.env', interpolate=False)
        check_runtime(root / 'data/private/bridge.sqlite3', root=root,
                      simulated=env.get('TESSERACT_BRIDGE_SIMULATION_ONLY') == '1')
        subprocess.run(['systemctl', 'start', unit.name], check=True)
    elif action == 'uninstall':
        subprocess.run(['systemctl', 'stop', unit.name], check=True)
        subprocess.run(['systemctl', 'disable', unit.name], check=True)
        destination.unlink()
        registry.unlink()
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
    else:
        raise SetupError('Unsupported service action.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('install', 'enable', 'start', 'uninstall'))
    parser.add_argument('--unit', required=True)
    parser.add_argument('--confirm', action='store_true')
    args = parser.parse_args()
    if not args.confirm:
        parser.error('Explicit --confirm is required for service mutations.')
    run(args.action, args.unit, Path(__file__).resolve().parents[1])


if __name__ == '__main__':
    main()
