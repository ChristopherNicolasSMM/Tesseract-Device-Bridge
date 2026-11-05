import base64
import io
import pytest
from dotenv import dotenv_values

from setup.app import create_app
from setup.state import InstallationState
from setup.infrastructure import DEFAULTS, prepare
from setup.security import prepare_security, SecurityError


def test_private_custom_none_and_generated_credentials(tmp_path, monkeypatch):
    from setup import infrastructure
    monkeypatch.setattr(infrastructure, 'probe_port', lambda *args: 'infra_port_available')
    state = InstallationState(tmp_path / 'new')
    try:
        state.start('en')
        with pytest.raises(SecurityError):
            prepare_security(state, 'generated')
        prepare(state, DEFAULTS)
        assert prepare_security(state, 'custom', 'x') is None
        assert state.value['credential_weak']
        env = dotenv_values(state.staging() / state.value['security_env'], interpolate=False)
        assert base64.b64decode(env['TESSERACT_BRIDGE_ADMIN_TOKEN_B64']).decode() == 'x'
        assert env['TESSERACT_BRIDGE_LOCAL_ADMIN'] == '0'
        prepare_security(state, 'none')
        env = dotenv_values(state.staging() / state.value['security_env'], interpolate=False)
        assert env['TESSERACT_BRIDGE_ADMIN_TOKEN_B64'] == ''
        assert env['TESSERACT_BRIDGE_LOCAL_ADMIN'] == '1'
        token = prepare_security(state, 'generated')
        assert len(token) >= 32
        assert token not in (state.directory / 'state.json').read_text(encoding='utf-8')
        assert not (state.root / '.env').exists()
        prepare(state, DEFAULTS)
        assert state.value['security_env'] is None
        assert not state.value['credential_configured']
    finally:
        state.close()


def test_generated_token_displayed_once_without_cookie_secret(tmp_path, monkeypatch):
    from setup import infrastructure
    monkeypatch.setattr(infrastructure, 'probe_port', lambda *args: 'infra_port_available')
    app = create_app(tmp_path / 'new')
    state = app.extensions['installation_state']
    try:
        state.start('en')
        prepare(state, DEFAULTS)
        client = app.test_client()
        base = 'http://127.0.0.1:8090'
        client.get('/security/', base_url=base)
        with client.session_transaction(base_url=base) as session:
            csrf = session['csrf']
        response = client.post('/security/save', base_url=base,
            headers={'Origin': base}, data={'csrf': csrf, 'mode': 'generated'})
        assert response.status_code == 303
        env = dotenv_values(state.staging() / state.value['security_env'], interpolate=False)
        token = base64.b64decode(env['TESSERACT_BRIDGE_ADMIN_TOKEN_B64']).decode()
        first = client.get('/security/', base_url=base)
        assert token.encode() in first.data
        assert token.encode() not in client.get('/security/', base_url=base).data
        with client.session_transaction(base_url=base) as session:
            assert token not in str(dict(session))
        denied = client.post('/security/save', base_url=base,
            headers={'Origin': base}, data={'csrf': csrf, 'mode': 'none'})
        assert denied.status_code == 409
    finally:
        state.close()
