"""Host integration of browser-only layout controls; no hardware operations."""
import re
from unittest.mock import MagicMock
from flask import Flask
from reusable.ui_preferences import register_layout
from reusable.documentation import DocumentLibrary
from reusable.documentation.web import register_documentation


def test_shared_assets_register_once_and_contain_no_administrative_routes():
    app = Flask(__name__)
    register_layout(app)
    register_layout(app)
    client = app.test_client()
    assert client.get('/layout-assets/layout.js').status_code == 200
    assert client.get('/layout-assets/layout.css').status_code == 200
    assert client.post('/layout-assets/layout.js').status_code == 405


def test_standalone_documentation_trusts_only_layout_nonce(tmp_path):
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs/test.md').write_text('# Test\n<script>alert("unsafe")</script>', encoding='utf-8')
    app = Flask(__name__)
    register_layout(app)
    register_documentation(app, DocumentLibrary(tmp_path, files=()), layout_control=True)
    client = app.test_client()
    response = client.get('/help/', query_string={'doc':'docs/test.md'})
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    nonce = re.search(r'nonce="([^"]+)"', text).group(1)
    assert "script-src 'nonce-" + nonce + "'" in response.headers['Content-Security-Policy']
    assert text.count('<script') == 1  # The document's script was sanitized away.
    assert 'data-layout-control' in text
    second = client.get('/help/').get_data(as_text=True)
    assert 'nonce="' + nonce + '"' not in second
    embedded = client.get('/help/', query_string={'doc':'docs/test.md', 'embedded':'1'})
    text = embedded.get_data(as_text=True)
    assert '<script' not in text
    assert 'data-layout-control' not in text
    assert 'data-layout-embedded="true"' in text
    assert 'name="embedded" value="1"' in text
    assert "script-src 'none'" in embedded.headers['Content-Security-Policy']


def test_panel_and_empty_configuration_have_controls_without_runtime_actions():
    from panel.app import create_panel_app
    from panel.configuration_app import create_configuration_app
    from config import BridgeConfig
    from storage.sqlite_store import INITIAL_CONFIG
    runtime = MagicMock()
    runtime.emergency_reason = None
    app = create_panel_app(BridgeConfig.from_dict(INITIAL_CONFIG), runtime)
    page = app.test_client().get('/').get_data(as_text=True)
    assert 'data-layout-surface="panel"' in page
    assert 'data-layout-control' in page
    assert 'data-layout-frame' in page
    runtime.trip.assert_not_called()
    empty = create_configuration_app(INITIAL_CONFIG)
    page = empty.test_client().get('/').get_data(as_text=True)
    assert 'data-layout-surface="configuration"' in page
    assert 'data-layout-control' in page


def test_setup_has_shared_control_and_keeps_documentation_csp(tmp_path):
    from setup.app import create_app
    app = create_app(tmp_path / 'clone')
    try:
        client = app.test_client()
        base = 'http://127.0.0.1:8090'
        page = client.get('/', base_url=base).get_data(as_text=True)
        assert 'data-layout-surface="wizard"' in page
        assert 'data-layout-control' in page
        documentation = client.get('/help/', base_url=base)
        assert "script-src 'nonce-" in documentation.headers['Content-Security-Policy']
    finally:
        app.extensions['installation_state'].close()
