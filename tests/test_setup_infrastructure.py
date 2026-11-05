import io
import socket

import pytest
from dotenv import dotenv_values

from setup.app import create_app
from setup.state import InstallationState
from setup.infrastructure import (
    DEFAULTS, DB_RELATIVE, InfrastructureError, validate, render_env, prepare, probe_port,
)


@pytest.mark.parametrize('key,value', [
    ('PANEL_HOST', 'http://localhost:8088'), ('PANEL_HOST', 'host\nTOKEN=x'),
    ('PANEL_HOST', 'bad/name'), ('PANEL_PORT', '0'), ('PANEL_PORT', '65536'),
    ('TEST_PANEL_PORT', 'invalid'), ('SIMULATION_ONLY', 'yes'),
])
def test_invalid_infrastructure_rejected(key, value):
    with pytest.raises(InfrastructureError):
        validate(dict(DEFAULTS, **{key: value}))


def test_render_env_preserves_comments_secrets_and_removes_duplicates():
    original = '# Keep comment\nTESSERACT_BRIDGE_ADMIN_TOKEN=private-test-value\nCUSTOM=keep\nTESSERACT_BRIDGE_PANEL_PORT=10\nTESSERACT_BRIDGE_PANEL_PORT=11\n'
    rendered = render_env(original, dict(DEFAULTS))
    assert '# Keep comment' in rendered
    assert 'CUSTOM=keep' in rendered
    parsed = dotenv_values(stream=io.StringIO(rendered), interpolate=False)
    assert parsed['TESSERACT_BRIDGE_ADMIN_TOKEN'] == 'private-test-value'
    assert parsed['TESSERACT_BRIDGE_DB'] == DB_RELATIVE
    assert parsed['TESSERACT_BRIDGE_STORAGE_MODE'] == 'orm'
    assert rendered.count('TESSERACT_BRIDGE_PANEL_PORT=') == 1


def test_busy_effective_port_and_setup_collision():
    with socket.socket() as occupied:
        occupied.bind(('127.0.0.1', 0))
        port = occupied.getsockname()[1]
        with pytest.raises(InfrastructureError):
            probe_port(dict(DEFAULTS, TEST_PANEL_PORT=str(port)), 8090)
    with pytest.raises(InfrastructureError):
        probe_port(dict(DEFAULTS, TEST_PANEL_PORT='8090'), 8090)


def test_staged_env_does_not_modify_active_or_create_database(tmp_path, monkeypatch):
    from setup import infrastructure
    monkeypatch.setattr(infrastructure, 'probe_port', lambda *args: 'infra_port_available')
    root = tmp_path / 'clone'
    root.mkdir()
    active = root / '.env'
    original = '# User configuration\nCUSTOM=preserved\n'
    active.write_text(original, encoding='utf-8')
    state = InstallationState(root)
    try:
        state.start('en')
        prepare(state, DEFAULTS)
        candidate = state.staging() / state.value['infrastructure_env']
        assert candidate.exists()
        assert active.read_text(encoding='utf-8') == original
        assert not list(root.rglob('*.sqlite3'))
        assert not state.value['infrastructure_ready']
        old_candidate = candidate
        def fail(*args):
            raise PermissionError('manifest write failed')
        monkeypatch.setattr(state, 'save', fail)
        with pytest.raises(PermissionError):
            prepare(state, dict(DEFAULTS, PANEL_PORT='8087'))
        assert state.staging() / state.value['infrastructure_env'] == old_candidate
        assert old_candidate.exists()
    finally:
        state.close()


def test_infrastructure_http_flow_and_no_secret_response(tmp_path, monkeypatch):
    from setup import infrastructure
    monkeypatch.setattr(infrastructure, 'probe_port', lambda *args: 'infra_port_available')
    root = tmp_path / 'clone'
    root.mkdir()
    (root / '.env').write_text('TESSERACT_BRIDGE_ADMIN_TOKEN=not-for-browser\n', encoding='utf-8')
    app = create_app(root)
    try:
        client = app.test_client()
        base = 'http://127.0.0.1:8090'
        client.get('/', base_url=base)
        with client.session_transaction(base_url=base) as session:
            csrf = session['csrf']
        client.post('/start', base_url=base, headers={'Origin': base},
                    data={'csrf': csrf, 'language': 'en'})
        page = client.get('/infrastructure/', base_url=base)
        assert page.status_code == 200
        assert b'not-for-browser' not in page.data
        response = client.post('/infrastructure/save', base_url=base,
            headers={'Origin': base}, data=dict(DEFAULTS, csrf=csrf))
        assert response.status_code == 303
        assert b'Configuration saved in staging' in client.get('/infrastructure/', base_url=base).data
        assert client.post('/infrastructure/save', base_url=base,
            headers={'Origin': base}, data=dict(DEFAULTS, csrf='wrong')).status_code == 403
        invalid = client.post('/infrastructure/save', base_url=base,
            headers={'Origin': base}, data=dict(DEFAULTS, csrf=csrf, PANEL_HOST='http://bad'))
        assert invalid.status_code == 409
        assert invalid.json['code'] == 'infra_invalid_host'
    finally:
        app.extensions['installation_state'].close()
