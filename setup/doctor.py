"""Read-only installation diagnostics. Never imports Flask, ORM, MQTT or GPIO."""
import argparse
import json
import platform
import sys
from pathlib import Path

from .version import SETUP_BUILD

STATUSES = {'new', 'in_progress', 'publishing', 'needs_review',
            'ready_simulated', 'ready_operational'}


def inspect_installation(root):
    root = Path(root).resolve()
    report = dict(build=SETUP_BUILD, python=platform.python_version(),
                  platform=platform.system(), venv=sys.prefix != sys.base_prefix,
                  env_present=(root / '.env').is_file(),
                  database_present=(root / 'data/private/bridge.sqlite3').is_file(),
                  setup_status='new', publication_status=None, issues=[])
    for relative, field in (('data/private/setup/state.json', 'setup_status'),
                            ('data/private/installation.json', 'publication_status')):
        path = root / relative
        if any(p.is_symlink() for p in [path] + list(path.parents) if p != root):
            report['issues'].append('linked_metadata')
            continue
        if not path.exists():
            continue
        try:
            if path.stat().st_size > 1024 * 1024:
                raise ValueError()
            value = json.loads(path.read_text(encoding='utf-8'))
            if (not isinstance(value, dict) or type(value.get('version')) is not int
                    or value['version'] != 1 or not isinstance(value.get('status'), str)
                    or value['status'] not in STATUSES):
                raise ValueError()
            report[field] = value['status']
        except (OSError, ValueError, UnicodeError):
            report['issues'].append('invalid_metadata')
    if report['publication_status'] == 'publishing':
        report['issues'].append('publication_incomplete')
    if report['publication_status'] in {'ready_simulated', 'ready_operational', 'needs_review'}:
        if not report['env_present'] or not report['database_present']:
            report['issues'].append('published_file_missing')
        if report['setup_status'] != report['publication_status']:
            report['issues'].append('state_needs_recovery')
    return report


def main():
    parser = argparse.ArgumentParser(description='Read-only, secret-free setup diagnostics')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    report = inspect_installation(args.root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report['issues'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
