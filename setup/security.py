"""Prepare administrative credentials privately; active .env is published later."""
import base64
import os
import secrets
import tempfile
from pathlib import Path

from flask import Blueprint, current_app, redirect, render_template, request, session

from .state import SetupError
from .i18n import catalog

bp = Blueprint('setup_security', __name__, url_prefix='/security')


class SecurityError(SetupError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def prepare_security(state, mode, token=''):
    if state.value['status'] != 'in_progress':
        raise SecurityError('security_start_first')
    name = state.value.get('infrastructure_env', '')
    if not name or Path(name).name != name:
        raise SecurityError('security_infra_first')
    source = state.staging() / name
    if source.is_symlink() or not source.is_file():
        raise SecurityError('security_infra_first')
    if mode not in ('generated', 'custom', 'none'):
        raise SecurityError('security_invalid_mode')
    if mode == 'generated':
        token = secrets.token_urlsafe(32)
    elif mode == 'none':
        token = ''
    if mode != 'none' and (not isinstance(token, str) or not token or len(token.encode('utf-8')) > 4096
                           or any(c in token for c in ('\r', '\n', '\x00'))):
        raise SecurityError('security_invalid_token')
    # Base64 is serialization, not encryption. It prevents dotenv interpolation
    # and permits Unicode/custom values without imposing a complexity requirement.
    updates = {'TESSERACT_BRIDGE_ADMIN_TOKEN': '',
               'TESSERACT_BRIDGE_ADMIN_TOKEN_B64': base64.b64encode(token.encode('utf-8')).decode('ascii'),
               'TESSERACT_BRIDGE_LOCAL_ADMIN': '1' if mode == 'none' else '0'}
    from reusable.guided_setup.configuration import update_env, ConfigurationError
    try:
        text = update_env(source.read_text(encoding='utf-8'), updates)
    except ConfigurationError as exc:
        raise SecurityError('security_infra_first') from exc
    fd, path = tempfile.mkstemp(prefix='security-', suffix='.env', dir=str(state.staging()))
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    weak = mode == 'custom' and len(token) < 16
    state.save(dict(state.value, security_env=Path(path).name, credential_mode=mode,
                    credential_weak=weak, credential_configured=True))
    return token if mode == 'generated' else None


def installation():
    state = current_app.extensions['installation_state']
    if state.value['status'] != 'in_progress':
        raise SecurityError('security_start_first')
    return state


@bp.get('/')
def page():
    state = installation()
    session.setdefault('csrf', secrets.token_urlsafe(32))
    reveal_id = session.pop('security_reveal', None)
    token = current_app.extensions.setdefault('setup_token_once', {}).pop(reveal_id, None)
    language = state.value['language']
    return render_template('security.html', t=catalog(language), language=language,
        theme=state.value.get('theme', 'light'), csrf=session['csrf'],
        mode=state.value.get('credential_mode') if state.value.get('credential_configured') else None,
        weak=state.value.get('credential_weak', False) if state.value.get('credential_configured') else False,
        generated_token=token, build=current_app.config['SETUP_BUILD'])


@bp.post('/save')
def save():
    state = installation()
    mode = request.form.get('mode', '')
    if mode == 'none' and request.form.get('confirm_local') != '1':
        raise SecurityError('security_confirm_local')
    token = prepare_security(state, mode, request.form.get('token', ''))
    if token is not None:
        # Never store plaintext token inside the signed client-side session.
        once = current_app.extensions.setdefault('setup_token_once', {})
        once.clear()
        reveal_id = secrets.token_urlsafe(24)
        once[reveal_id] = token
        session['security_reveal'] = reveal_id
    return redirect('/security/', code=303)
