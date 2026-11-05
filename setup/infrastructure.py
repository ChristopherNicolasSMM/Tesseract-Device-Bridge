"""Validate infrastructure and prepare .env privately; never modify the active installation."""
import errno
import hashlib
import io
import ipaddress
import os
import re
import socket
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
    for key in ('TEST_PANEL_PORT', 'PANEL_PORT'):
        if not re.fullmatch(r'[0-9]{1,5}', result[key]) or not 1 <= int(result[key]) <= 65535:
            raise InfrastructureError('infra_invalid_port')
        result[key] = str(int(result[key]))
    host = result['PANEL_HOST']
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if (len(host) > 253 or not host or re.fullmatch(r'[0-9.]+', host) or
                any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', part)
                    for part in host.rstrip('.').split('.'))):
            raise InfrastructureError('infra_invalid_host')
    return result


def probe_port(values, setup_port):
    simulated = values['SIMULATION_ONLY'] == '1'
    host = '127.0.0.1' if simulated else values['PANEL_HOST']
    port = int(values['TEST_PANEL_PORT'] if simulated else values['PANEL_PORT'])
    if port == setup_port:
        raise InfrastructureError('infra_port_busy')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # Do not contact DNS or bind to an unverified remote hostname.
        return 'infra_port_unchecked'
    family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            if os.name == 'nt' and hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind((str(address), port))
    except OSError as exc:
        if exc.errno == errno.EADDRNOTAVAIL:
            return 'infra_port_unchecked'
        raise InfrastructureError('infra_port_busy') from exc
    return 'infra_port_available'


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
    from dotenv.parser import parse_stream
    values = validate(values)
    updates = {PREFIX + key: value for key, value in values.items()}
    updates[PREFIX + 'DB'] = DB_RELATIVE
    updates[PREFIX + 'STORAGE_MODE'] = 'orm'
    output, written = [], set()
    for binding in parse_stream(io.StringIO(original)):
        if binding.error:
            raise InfrastructureError('infra_env_invalid')
        key = binding.key
        if key in updates:
            if key not in written:
                output.append(key + '=' + updates[key] + '\n')
                written.add(key)
        else:
            output.append(binding.original.string)
    text = ''.join(output)
    if text and not text.endswith('\n'):
        text += '\n'
    for key, value in updates.items():
        if key not in written:
            text += key + '=' + value + '\n'
    return text


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
                        infrastructure_db=DB_RELATIVE, infrastructure_ready=False))
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
