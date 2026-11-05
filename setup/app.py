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
    origin = "http://127.0.0.1:" + str(port)
    translations = {}
    for language in ("pt_BR", "en"):
        translations[language] = json.loads(
            (Path(__file__).parent / "translations" / (language + ".json")).read_text(encoding="utf-8"))

    @app.before_request
    def local_boundary():
        try:
            local = ipaddress.ip_address(request.remote_addr or "").is_loopback
        except ValueError:
            local = False
        if not local or request.host != "127.0.0.1:" + str(port):
            abort(403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            expected = session.get("csrf", "")
            received = request.form.get("csrf", "")
            if (request.headers.get("Origin") != origin or not expected
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
