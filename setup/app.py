"""Local setup HTTP boundary; never imports the operational panel or runtime."""
from __future__ import annotations

import ipaddress
import json
import platform
import secrets
import sys
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, session

from .state import InstallationState, SetupError


def create_app(root=None, *, port=8090):
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    state = InstallationState(root)
    app = Flask(__name__)
    app.secret_key = secrets.token_bytes(32)
    app.config.update(MAX_CONTENT_LENGTH=16 * 1024, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE="Strict", SESSION_COOKIE_NAME="bridge_setup")
    app.extensions["installation_state"] = state
    local_hosts = {"127.0.0.1:" + str(port), "localhost:" + str(port),
                   "[::1]:" + str(port)}
    translations = {}
    for language in ("pt_BR", "en"):
        translations[language] = json.loads(
            (Path(__file__).parent / "translations" / (language + ".json")).read_text(encoding="utf-8"))

    @app.before_request
    def local_boundary():
        try:
            address = ipaddress.ip_address(request.remote_addr or "")
            mapped = getattr(address, "ipv4_mapped", None)
            local = (mapped or address).is_loopback
        except ValueError:
            local = False
        if not local:
            app.logger.warning("Setup rejected a non-loopback connection")
            abort(403, description="Setup requires a local connection or SSH tunnel.")
        if request.host.lower() not in local_hosts:
            app.logger.warning("Setup rejected Host %r; expected a loopback host on port %s",
                               request.host, port)
            abort(403, description="Open http://127.0.0.1:" + str(port)
                  + " or http://localhost:" + str(port))
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            expected = session.get("csrf", "")
            received = request.form.get("csrf", "")
            if (request.headers.get("Origin") != "http://" + request.host.lower() or not expected
                    or not secrets.compare_digest(expected, received)):
                abort(403)

    @app.after_request
    def headers(response):
        response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                 "Referrer-Policy": "no-referrer",
                                 "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"})
        return response

    @app.get("/")
    def index():
        session.setdefault("csrf", secrets.token_urlsafe(32))
        language = state.value["language"]
        return render_template("index.html", t=translations[language], language=language,
                               state=state.value, csrf=session["csrf"],
                               system=platform.system(), python=platform.python_version(),
                               venv=sys.prefix != sys.base_prefix)

    @app.post("/start")
    def start():
        from flask import redirect
        state.start(request.form.get("language"))
        return redirect("/", code=303)

    @app.post("/clean")
    def clean():
        from .bootstrap import bootstrap_empty
        from flask import redirect
        bootstrap_empty(state)
        return redirect("/", code=303)

    @app.post("/abort")
    def cancel():
        from flask import redirect
        state.abort()
        return redirect("/", code=303)

    @app.errorhandler(OSError)
    @app.errorhandler(SetupError)
    def setup_error(exc):
        # Never render paths, imported data or credentials in HTTP errors.
        return jsonify(code="setup_state_error", message=translations[state.value["language"]]["error"]), 409

    return app
