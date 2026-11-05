"""Local maintenance CLI for legacy discovery/import; no HTTP file access."""
import argparse
import json
from pathlib import Path

from .state import InstallationState
from .i18n import translate_report, translate
from .legacy import discover, import_directory


def _main():
    parser = argparse.ArgumentParser(description='Discover/import legacy files into setup staging')
    parser.add_argument('--source', required=True)
    parser.add_argument('--language', choices=('pt_BR', 'en'), default='pt_BR')
    parser.add_argument('--import-data', action='store_true')
    parser.add_argument('--sqlite', action='store_true', help='Import a clean SQLite snapshot instead of a directory')
    parser.add_argument('--allow-partial', action='store_true', help='Preserve valid entities; rejected data requires review')
    parser.add_argument('--select', action='append', help='Relative supported path; repeat to select multiple files')
    parser.add_argument('--disable-invalid-remote-control', action='store_true')
    args = parser.parse_args()
    if args.sqlite and not args.import_data:
        parser.error('--sqlite requires --import-data (inspection is performed on a private copy)')
    if args.sqlite and (args.select or args.disable_invalid_remote_control or args.allow_partial):
        parser.error('--select and --disable-invalid-remote-control apply only to YAML/JSON')
    if not args.import_data:
        print(json.dumps(discover(args.source), ensure_ascii=False, indent=2))
        return
    state = InstallationState(Path(__file__).resolve().parents[1])
    try:
        state.start(args.language)
        if args.sqlite:
            from .sqlite_import import import_sqlite
            result = import_sqlite(state, args.source)
        else:
            result = import_directory(state, args.source, selected=args.select,
                disable_invalid_remote_control=args.disable_invalid_remote_control,
                allow_partial=args.allow_partial)
        print(json.dumps(translate_report(result, args.language), ensure_ascii=False, indent=2))
    finally:
        state.close()


def main():
    import sys
    try:
        return _main()
    except Exception:
        language = 'pt_BR'
        if '--language' in sys.argv:
            index = sys.argv.index('--language') + 1
            if index < len(sys.argv) and sys.argv[index] in ('pt_BR', 'en'):
                language = sys.argv[index]
        print(json.dumps({'code': 'import_failed',
                          'message': translate(language, 'import_failed')}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
