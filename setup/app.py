"""Local setup HTTP boundary; never imports the operational panel or runtime."""
from __future__ import annotations

import ipaddress
import json
import platform
import secrets
import sys
from urllib.parse import urlsplit
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, session

from .state import InstallationState, SetupError
from .i18n import catalog
from .version import SETUP_BUILD
from werkzeug.exceptions import HTTPException


def create_app(root=None, *, port=8090):
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    state = InstallationState(root)
    app = Flask(__name__)
    from shared_ui import register_ui
    register_ui(app)
    from reusable.guided_setup.web import WizardStep, register_wizard_ui
    register_wizard_ui(app, [
        WizardStep('language', '/', 'step_language'),
        WizardStep('data', '/import/', 'step_data'),
        WizardStep('infrastructure', '/infrastructure/', 'infrastructure'),
        WizardStep('security', '/security/', 'security'),
        WizardStep('finish', '/finish/', 'step_finish'),
    ])
    app.config["SETUP_BUILD"] = SETUP_BUILD
    app.config["SETUP_PORT"] = port
    app.secret_key = secrets.token_bytes(32)
    app.config.update(MAX_CONTENT_LENGTH=257 * 1024 * 1024, MAX_FORM_PARTS=120, MAX_FORM_MEMORY_SIZE=512 * 1024, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE="Strict", SESSION_COOKIE_NAME="bridge_setup_" + str(port))
    app.extensions["installation_state"] = state
    from .browser_import import bp as import_bp
    app.register_blueprint(import_bp)
    from .infrastructure import bp as infrastructure_bp
    app.register_blueprint(infrastructure_bp)
    from .security import bp as security_bp
    app.register_blueprint(security_bp)
    from .finalize import bp as finish_bp
    app.register_blueprint(finish_bp)
    local_hosts = {"127.0.0.1:" + str(port), "localhost:" + str(port),
                   "[::1]:" + str(port)}
    translations = {language: catalog(language) for language in ('pt_BR', 'en')}

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
            received = request.headers.get("X-Setup-CSRF") or request.form.get("csrf", "")
            origin = request.headers.get("Origin")
            expected_origin = "http://" + request.host.lower()
            # Some browser policies omit Origin on same-origin form submissions.
            # Accept only an exact same-origin Referer as a fallback, still with CSRF.
            if origin is None:
                ref = urlsplit(request.headers.get("Referer", ""))
                origin = ref.scheme + "://" + ref.netloc.lower() if ref.netloc else None
            if origin != expected_origin:
                app.logger.warning("Setup rejected form: origin/referer mismatch")
                abort(403)
            if not expected or not secrets.compare_digest(expected, received):
                app.logger.warning("Setup rejected form: session/CSRF mismatch; reload the page")
                abort(403)
            receipt = state.root / "data/private/installation.json"
            if (receipt.exists() or receipt.is_symlink()) and request.path not in (
                    "/finish/recover", "/finish/rollback", "/finish/revalidate", "/finish/service", "/finish/close", "/appearance", "/abort"):
                raise SetupError("Publication exists; use completion/recovery.")


    @app.after_request
    def headers(response):
        if response.status_code == 303 and request.headers.get("X-Setup-CSRF"):
            # Let fetch navigate once; following a redirect here would consume flash notices.
            response = jsonify(redirect=response.headers["Location"])
        response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                 "Referrer-Policy": "same-origin",
                                 "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"})
        return response

    @app.get("/setup-version")
    def version():
        return jsonify(build=app.config["SETUP_BUILD"])

    @app.get("/")
    def index():
        session.setdefault("csrf", secrets.token_urlsafe(32))
        language = state.value["language"]
        return render_template("index.html", t=translations[language], language=language,
                               state=state.value, csrf=session["csrf"],
                               system=platform.system(), python=platform.python_version(),
                               venv=sys.prefix != sys.base_prefix,
                               theme=state.value.get("theme", "light"), notice=session.pop("notice", None),
                               build=app.config["SETUP_BUILD"])

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
        session["notice"] = "prepared"
        return redirect("/", code=303)

    @app.post("/appearance")
    def appearance():
        from flask import redirect
        theme = request.form.get("theme")
        if theme not in ("light", "dark"):
            raise SetupError("Unsupported theme.")
        state.save(dict(state.value, theme=theme))
        return redirect("/", code=303)

    @app.post("/abort")
    def cancel():
        from flask import redirect
        state.abort()
        return redirect("/", code=303)

    @app.errorhandler(HTTPException)
    def http_error(exc):
        code = {403: "forbidden", 404: "not_found", 413: "too_large"}.get(exc.code, "request_error")
        return jsonify(code=code, message=translations[state.value["language"]][code]), exc.code

    @app.errorhandler(Exception)
    def internal_error(exc):
        app.logger.error("Setup request failed; imported content omitted from logs")
        return jsonify(code="request_error", message=translations[state.value["language"]]["request_error"]), 500

    @app.errorhandler(OSError)
    @app.errorhandler(SetupError)
    def setup_error(exc):
        # Never render paths, imported data or credentials in HTTP errors.
        code = getattr(exc, "code", "error")
        message = translations[state.value["language"]].get(code, translations[state.value["language"]]["error"])
        details = {}
        if code == 'abort_files_busy':
            # Never return raw exception text or an absolute filesystem path.
            if getattr(exc, 'temporary_file', None):
                details['file'] = exc.temporary_file
                message += ' ' + translations[state.value['language']]['abort_blocked_file'].format(file=exc.temporary_file)
            if isinstance(getattr(exc, 'os_error', None), int):
                details['os_error'] = exc.os_error
                message += ' (' + str(exc.os_error) + ')'
        return jsonify(code=code, message=message, details=details), 409

    return app
