"""Local maintenance CLI for legacy discovery/import; no HTTP file access."""
import argparse
import json
from pathlib import Path

from .state import InstallationState
from .legacy import discover, import_directory


def main():
    parser = argparse.ArgumentParser(description='Discover/import legacy files into setup staging')
    parser.add_argument('--source', required=True)
    parser.add_argument('--import-data', action='store_true')
    parser.add_argument('--select', action='append', help='Relative supported path; repeat to select multiple files')
    parser.add_argument('--disable-invalid-remote-control', action='store_true')
    args = parser.parse_args()
    if not args.import_data:
        print(json.dumps(discover(args.source), ensure_ascii=False, indent=2))
        return
    state = InstallationState(Path(__file__).resolve().parents[1])
    try:
        state.start(state.value['language'])
        result = import_directory(state, args.source, selected=args.select,
            disable_invalid_remote_control=args.disable_invalid_remote_control)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        state.close()


if __name__ == '__main__':
    main()
