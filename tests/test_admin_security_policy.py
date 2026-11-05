import base64
import pytest

from config import BridgeConfig
from device_runtime import DeviceRuntime
from gpio.simulated_backend import SimulatedGPIOBackend
from panel.app import create_panel_app
from storage import sqlite_store as store


@pytest.fixture
def admin(monkeypatch):
    for name in ('TESSERACT_BRIDGE_ADMIN_TOKEN', 'TESSERACT_BRIDGE_ADMIN_TOKEN_B64',
                 'TESSERACT_BRIDGE_LOCAL_ADMIN'):
        monkeypatch.delenv(name, raising=False)
    config = BridgeConfig.from_dict(store.load_config())
    runtime = DeviceRuntime(config, SimulatedGPIOBackend())
    app = create_panel_app(config, runtime)
    app.testing = True
    yield app.test_client(), config
    runtime.shutdown()


def test_legacy_without_token_remains_disabled(admin):
    client, config = admin
    assert client.get('/api/admin/config').status_code == 503


def test_short_and_unicode_token_supported(admin, monkeypatch):
    client, config = admin
    monkeypatch.setenv('TESSERACT_BRIDGE_ADMIN_TOKEN', 'x')
    assert client.get('/api/admin/config', headers={'X-Bridge-Admin-Token': 'x'}).status_code == 200
    monkeypatch.setenv('TESSERACT_BRIDGE_ADMIN_TOKEN_B64', base64.b64encode('meu-token-é-€'.encode()).decode())
    headers = {'X-Bridge-Admin-Token': base64.b64encode('meu-token-é-€'.encode()).decode(),
               'X-Bridge-Admin-Token-Encoding': 'base64utf8'}
    assert client.get('/api/admin/config', headers=headers).status_code == 200
    assert client.get('/api/admin/config', headers={'X-Bridge-Admin-Token': 'x'}).status_code == 401


def test_local_policy_requires_csrf_for_writes(admin, monkeypatch):
    client, config = admin
    monkeypatch.setenv('TESSERACT_BRIDGE_LOCAL_ADMIN', '1')
    base = 'http://127.0.0.1:' + str(config.panel.port)
    session = client.get('/api/admin/security/session', base_url=base)
    assert session.status_code == 200
    assert session.json['mode'] == 'local'
    payload = client.get('/api/admin/config', base_url=base).json['config']
    assert client.post('/api/admin/drafts', base_url=base, json=payload).status_code == 403
    headers = {'Origin': base, 'X-Bridge-Admin-CSRF': session.json['csrf']}
    assert client.post('/api/admin/drafts', base_url=base, headers=headers, json=payload).status_code == 201
    headers['Origin'] = 'http://evil.example'
    assert client.post('/api/admin/drafts', base_url=base, headers=headers, json=payload).status_code == 403


@pytest.mark.parametrize('host,remote,headers', [
    ('127.0.0.1', '10.0.0.1', {}),
    ('evil.example', '127.0.0.1', {}),
    ('127.0.0.1', '127.0.0.1', {'X-Forwarded-For': '127.0.0.1'}),
    ('127.0.0.1', '127.0.0.1', {'Sec-Fetch-Site': 'cross-site'}),
])
def test_local_admin_rejects_remote_rebinding_and_proxy(admin, monkeypatch, host, remote, headers):
    client, config = admin
    monkeypatch.setenv('TESSERACT_BRIDGE_LOCAL_ADMIN', '1')
    base = 'http://' + host + ':' + str(config.panel.port)
    response = client.get('/api/admin/config', base_url=base, headers=headers,
                          environ_overrides={'REMOTE_ADDR': remote})
    assert response.status_code == 403


def test_local_policy_forces_loopback_at_launch(admin, monkeypatch):
    from storage.launch_config import load_runtime_config
    monkeypatch.setattr('storage.launch_config.load_infra_env', lambda: False)
    monkeypatch.setenv('TESSERACT_BRIDGE_LOCAL_ADMIN', '1')
    monkeypatch.setenv('TESSERACT_BRIDGE_PANEL_HOST', '0.0.0.0')
    assert load_runtime_config().panel.host == '127.0.0.1'


def test_invalid_encoded_credential_does_not_fall_back_to_local(admin, monkeypatch):
    client, config = admin
    monkeypatch.setenv('TESSERACT_BRIDGE_ADMIN_TOKEN_B64', 'not-base64!')
    monkeypatch.setenv('TESSERACT_BRIDGE_LOCAL_ADMIN', '1')
    assert client.get('/api/admin/config').status_code == 503
