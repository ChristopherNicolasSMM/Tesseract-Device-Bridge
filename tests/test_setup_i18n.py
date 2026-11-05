import json
from pathlib import Path
from setup.app import create_app
from setup.i18n import catalog, translate_report


def test_catalog_keys_and_event_messages():
    assert set(catalog('pt_BR')) == set(catalog('en'))
    report = {'events': [{'category': 'warning', 'code': 'file_rejected'}]}
    displayed = translate_report(report, 'pt_BR')
    assert displayed['events'][0]['message'] != 'file_rejected'
    assert 'message' not in report['events'][0]


def test_localized_errors_styles_and_theme_persist(tmp_path):
    # The autouse legacy fixture owns tmp_path/isolated-bridge.sqlite3.
    # Give the installer a separate root and assert only its own effects.
    setup_root = tmp_path / 'setup-clone'
    app = create_app(setup_root)
    state = app.extensions['installation_state']
    try:
        client = app.test_client()
        base = 'http://127.0.0.1:8090'
        page = client.get('/', base_url=base)
        assert b'/shared-ui/theme.css' in page.data
        assert client.get('/shared-ui/theme.css', base_url=base).status_code == 200
        assert client.get('/static/setup.css', base_url=base).status_code == 200
        with client.session_transaction(base_url=base) as session:
            csrf = session['csrf']
        headers = {'Origin': base}
        client.post('/start', base_url=base, headers=headers, data={'csrf': csrf, 'language': 'en'})
        response = client.post('/appearance', base_url=base, headers=headers, data={'csrf': csrf, 'theme': 'light'})
        assert response.status_code == 303
        assert b'data-theme="light"' in client.get('/', base_url=base).data
        assert client.get('/missing', base_url=base).json['message'] == catalog('en')['not_found']
        assert state.value['theme'] == 'light'
        assert not list(setup_root.rglob('*.sqlite3'))
    finally:
        state.close()
    again = create_app(setup_root)
    try:
        assert again.extensions['installation_state'].value['theme'] == 'light'
    finally:
        again.extensions['installation_state'].close()
