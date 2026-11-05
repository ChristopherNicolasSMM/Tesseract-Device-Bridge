"""Validate infrastructure and prepare .env privately; never modify the active installation."""
import hashlib
import io
import os
import tempfile
from pathlib import Path

from flask import Blueprint, current_app, redirect, render_template, request, session

from .state import SetupError
from .i18n import catalog

bp = Blueprint('setup_infrastructure', __name__, url_prefix='/infrastructure')
PREFIX = 'TESSERACT_BRIDGE_'
KEYS = ('SIMULATION_ONLY', 'TEST_PANEL_PORT', 'PANEL_HOST', 'PANEL_PORT')
DEFAULTS = dict(SIMULATION_ONLY='1', TEST_PANEL_PORT='8089', PANEL_HOST='127.0.0.1', PANEL_PORT='8088')
DB_RELATIVE = './data/private/bridge.sqlite3'


class InfrastructureError(SetupError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def validate(values):
    result = {key: str(values.get(key, DEFAULTS[key])).strip() for key in KEYS}
    if result['SIMULATION_ONLY'] not in ('0', '1'):
        raise InfrastructureError('infra_invalid_mode')
    from reusable.guided_setup.configuration import port_number, host_name, ConfigurationError
    try:
        for key in ('TEST_PANEL_PORT', 'PANEL_PORT'):
            result[key] = port_number(result[key])
        result['PANEL_HOST'] = host_name(result['PANEL_HOST'])
    except ConfigurationError as exc:
        raise InfrastructureError('infra_' + str(exc)) from exc
    return result


def probe_port(values, setup_port):
    from reusable.guided_setup.configuration import probe_bind, ConfigurationError
    simulated = values['SIMULATION_ONLY'] == '1'
    host = '127.0.0.1' if simulated else values['PANEL_HOST']
    port = values['TEST_PANEL_PORT'] if simulated else values['PANEL_PORT']
    try:
        return 'infra_' + probe_bind(host, port, reserved_ports=(setup_port,))
    except ConfigurationError as exc:
        raise InfrastructureError('infra_' + str(exc)) from exc


def existing_env(root):
    path = Path(root) / '.env'
    if path.is_symlink():
        raise InfrastructureError('infra_env_invalid')
    if not path.exists():
        return '', None
    if path.stat().st_size > 1024 * 1024:
        raise InfrastructureError('infra_env_invalid')
    raw = path.read_bytes()
    try:
        text = raw.decode('utf-8')
    except UnicodeError as exc:
        raise InfrastructureError('infra_env_invalid') from exc
    return text, hashlib.sha256(raw).hexdigest()


def render_env(original, values):
    from reusable.guided_setup.configuration import update_env, ConfigurationError
    values = validate(values)
    updates = {PREFIX + key: value for key, value in values.items()}
    updates[PREFIX + 'DB'] = DB_RELATIVE
    updates[PREFIX + 'STORAGE_MODE'] = 'orm'
    try:
        return update_env(original, updates)
    except ConfigurationError as exc:
        raise InfrastructureError('infra_env_invalid') from exc


def initial_values(state):
    from dotenv import dotenv_values
    saved = state.value.get('infrastructure')
    if isinstance(saved, dict):
        return saved
    original, _ = existing_env(state.root)
    parsed = dotenv_values(stream=io.StringIO(original), interpolate=False)
    # Never expose token, MQTT passwords or other unrelated variables.
    return {key: parsed.get(PREFIX + key) or default for key, default in DEFAULTS.items()}


def prepare(state, values, *, setup_port=8090):
    if state.value['status'] != 'in_progress':
        raise InfrastructureError('infra_start_first')
    values = validate(values)
    port_status = probe_port(values, setup_port)
    original, digest = existing_env(state.root)
    text = render_env(original, values)
    directory = state.staging()
    # Each revision is immutable. A failed manifest write cannot invalidate
    # the previously selected environment candidate.
    fd, name = tempfile.mkstemp(prefix='infrastructure-', suffix='.env', dir=str(directory))
    target = Path(name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        state.save(dict(state.value, infrastructure=values, infrastructure_env=target.name,
                        infrastructure_source_sha256=digest, infrastructure_port_status=port_status,
                        infrastructure_db=DB_RELATIVE, infrastructure_ready=False,
                        security_env=None, credential_configured=False))
    except BaseException:
        # Keep the immutable candidate as private recovery evidence; never
        # delete anything that might already be referenced by the manifest.
        raise
    return values


def installation():
    value = current_app.extensions['installation_state']
    if value.value['status'] != 'in_progress':
        raise InfrastructureError('infra_start_first')
    return value


@bp.get('/')
def page():
    value = installation()
    session.setdefault('csrf', __import__('secrets').token_urlsafe(32))
    language = value.value['language']
    return render_template('infrastructure.html', t=catalog(language), language=language,
        theme=value.value.get('theme', 'light'), csrf=session['csrf'],
        values=initial_values(value), db_path=DB_RELATIVE,
        saved=bool(value.value.get('infrastructure_env')),
        port_status=value.value.get('infrastructure_port_status'),
        build=current_app.config['SETUP_BUILD'])


@bp.post('/save')
def save():
    value = installation()
    prepare(value, request.form, setup_port=current_app.config['SETUP_PORT'])
    return redirect('/infrastructure/', code=303)
