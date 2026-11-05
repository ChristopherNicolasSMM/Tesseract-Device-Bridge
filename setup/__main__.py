"""Run the installation wizard without loading .env or the Bridge."""
import argparse
import sys

from werkzeug.serving import make_server

from .app import create_app
from .state import SetupError


def main():
    parser = argparse.ArgumentParser(description="Tesseract Device Bridge setup (local only)")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")
    app = None
    try:
        app = create_app(port=args.port)
        # No development debugger/reloader; one process owns the installation lock.
        server = make_server("127.0.0.1", args.port, app)
        print("Setup build: " + app.config["SETUP_BUILD"], flush=True)
        print("Setup: http://127.0.0.1:" + str(args.port), flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()
    except KeyboardInterrupt:
        return 0
    except (OSError, SetupError, ValueError) as exc:
        print("Setup could not start: " + str(exc), file=sys.stderr)
        return 1
    finally:
        if app is not None:
            app.extensions["installation_state"].close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
