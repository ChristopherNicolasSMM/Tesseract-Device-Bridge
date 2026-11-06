import io
import json
from pathlib import Path
import pytest
import yaml

from setup.app import create_app


@pytest.fixture
def browser(tmp_path):
    app = create_app(tmp_path / 'new')
    app.config['TESTING'] = True
    client = app.test_client()
    base = 'http://localhost:8090'
    client.get('/', base_url=base)
    with client.session_transaction(base_url=base) as session:
        csrf = session['csrf']
    response = client.post('/start', base_url=base, headers={'Origin': base},
                           data={'csrf': csrf, 'language': 'en'})
    assert response.status_code == 303
    yield app, client, base, csrf
    app.extensions['installation_state'].close()


def test_browser_source_preview_import_and_abort(browser, tmp_path):
    from storage.sqlite_store import INITIAL_CONFIG
    import copy
    app, client, base, csrf = browser
    source = tmp_path / 'old'
    source.mkdir()
    config = copy.deepcopy(INITIAL_CONFIG)
    config['mqtt']['password'] = 'never-expose-this'
    original = yaml.safe_dump(config)
    (source / 'devices.yml').write_text(original, encoding='utf-8')
    response = client.post('/import/discover', base_url=base, headers={'Origin': base},
        data={'csrf': csrf, 'source': str(source), 'kind': 'directory'})
    assert response.status_code == 303
    page = client.get('/import/', base_url=base)
    assert b'devices.yml' in page.data
    assert b'never-expose-this' not in page.data
    desc = app.extensions['installation_state'].value['browser_source']
    entry = next(r['id'] for r in desc['rows'] if r['path'] == 'devices.yml')
    preview = client.get('/import/preview/' + entry, base_url=base)
    assert preview.status_code == 200
    assert 'never-expose-this' not in preview.json['text']
    assert '[REDACTED]' in preview.json['text']
    response = client.post('/import/run', base_url=base, headers={'Origin': base},
                          data={'csrf': csrf, 'selected': [entry]})
    assert response.status_code == 303
    report = app.extensions['installation_state'].value['browser_report']
    assert report['database']
    assert not report['runtime_authorized']
    assert (source / 'devices.yml').read_text(encoding='utf-8') == original
    response = client.post('/import/acknowledge', base_url=base, headers={'Origin': base}, data={'csrf': csrf})
    assert response.status_code == 303
    state = app.extensions['installation_state']
    staging = state.staging()
    assert state.value['browser_acknowledged']
    client.post('/abort', base_url=base, headers={'Origin': base}, data={'csrf': csrf})
    assert not staging.exists()


def test_browser_upload_and_traversal(browser):
    from storage.sqlite_store import INITIAL_CONFIG
    app, client, base, csrf = browser
    response = client.post('/import/upload', base_url=base, headers={'Origin': base},
        data={'csrf': csrf, 'kind': 'files',
              'files': (io.BytesIO(yaml.safe_dump(INITIAL_CONFIG).encode()), 'devices.yml')},
        content_type='multipart/form-data')
    assert response.status_code == 303
    assert app.extensions['installation_state'].value['browser_source']['kind'] == 'upload'
    response = client.post('/import/upload', base_url=base, headers={'Origin': base},
        data={'csrf': csrf, 'files': (io.BytesIO(b'bad'), '../devices.yml')},
        content_type='multipart/form-data')
    assert response.status_code == 409


def test_referer_fallback_and_cross_origin_denied(browser):
    app, client, base, csrf = browser
    data = {'csrf': csrf, 'theme': 'light'}
    assert client.post('/appearance', base_url=base, headers={'Referer': base + '/'}, data=data).status_code == 303
    assert client.post('/appearance', base_url=base, headers={'Origin': 'http://evil.example', 'Referer': base + '/'}, data=data).status_code == 403
    assert client.post('/appearance', base_url=base, headers={'Origin': base},
                       data={'csrf': 'wrong', 'theme': 'light'}).status_code == 403


def test_assets_version_and_fetch_redirect(browser):
    app, client, base, csrf = browser
    assert client.get('/setup-version', base_url=base).json['build'] == app.config['SETUP_BUILD']
    for url in ['/static/setup.css', '/static/setup.js', '/shared-ui/theme.css']:
        assert client.get(url, base_url=base).status_code == 200
    response = client.post('/appearance', base_url=base,
        headers={'Origin': base, 'X-Setup-CSRF': csrf}, data={'theme': 'light'})
    assert response.status_code == 200
    assert response.json['redirect'] == '/'


def test_upload_sqlite_browser(browser, tmp_path):
    from storage.sqlite_store import initialize
    app, client, base, csrf = browser
    old = tmp_path / 'old.sqlite3'
    initialize(path=old)
    raw = old.read_bytes()
    response = client.post('/import/upload', base_url=base, headers={'Origin': base},
        data={'csrf': csrf, 'kind': 'sqlite', 'files': (io.BytesIO(raw), 'old.sqlite3')},
        content_type='multipart/form-data')
    assert response.status_code == 303
    response = client.post('/import/run', base_url=base, headers={'Origin': base},
        data={'csrf': csrf, 'selected': ['0']})
    assert response.status_code == 303
    report = app.extensions['installation_state'].value['browser_report']
    assert report['source_kind'] == 'legacy'
    assert old.read_bytes() == raw


def test_preview_malformed_and_recursive_redaction(browser, tmp_path):
    from setup.browser_import import parse_preview, redact
    from setup.state import SetupError
    recursive = []
    recursive.append(recursive)
    with pytest.raises(SetupError):
        redact(recursive)
    p = tmp_path / 'bad.yml'
    p.write_text('!!python/object/apply:os.system [echo nope]', encoding='utf-8')
    with pytest.raises(yaml.YAMLError):
        parse_preview(p)


def test_successive_uploads_preserve_inventory_and_reject_duplicates(browser):
    app, client, base, csrf = browser
    state = app.extensions['installation_state']
    def upload(name, content, destination=''):
        return client.post('/import/upload', base_url=base,
            headers={'Origin': base}, content_type='multipart/form-data',
            data={'csrf': csrf, 'kind': 'files', 'destination': destination,
                  'files': (io.BytesIO(content), name)})
    assert upload('devices.yml', b'devices: []').status_code == 303
    first = Path(state.value['browser_source']['root'])
    original = (first / 'devices.yml').read_bytes()
    assert upload('receita.json', b'[]', 'data/public/receita.json').status_code == 303
    desc = state.value['browser_source']
    assert {row['path'] for row in desc['rows']} == {'devices.yml', 'data/public/receita.json'}
    assert (Path(desc['root']) / 'devices.yml').read_bytes() == original
    assert (first / 'devices.yml').read_bytes() == original
    assert upload('devices.yml', b'devices: changed').status_code == 409
    assert state.value['browser_source'] == desc
    assert (Path(desc['root']) / 'devices.yml').read_bytes() == original


def test_directory_inventory_excludes_unrelated_files(browser, tmp_path):
    app, client, base, csrf = browser
    source = tmp_path / 'previous-clone'
    (source / 'data/private').mkdir(parents=True)
    (source / 'devices.yml').write_text('devices: []', encoding='utf-8')
    (source / 'README.md').write_text('not an import', encoding='utf-8')
    (source / '.gitignore').write_text('not an import', encoding='utf-8')
    (source / 'unrelated.json').write_text('{}', encoding='utf-8')
    (source / 'data/private/sensor_calibration.json').write_text('{}', encoding='utf-8')
    result = client.post('/import/discover', base_url=base, headers={'Origin': base},
        data={'csrf': csrf, 'source': '"' + str(source) + '"', 'kind': 'directory'})
    assert result.status_code == 303
    desc = app.extensions['installation_state'].value['browser_source']
    assert {row['path'] for row in desc['rows']} == {'devices.yml', 'data/private/sensor_calibration.json'}
    page = client.get('/import/', base_url=base)
    assert b'README.md' not in page.data
    assert b'.gitignore' not in page.data
    assert b'unrelated.json' not in page.data
    # The engine still records ignored entries in its own discovery/report contract.
    from setup.legacy import discover
    assert any(row['path'] == 'README.md' and row['status'] == 'ignored' for row in discover(source))


def test_folder_navigation_requires_csrf_and_returns_only_directories(browser, tmp_path):
    app, client, base, csrf = browser
    source = tmp_path / 'old project with spaces'
    (source / 'data').mkdir(parents=True)
    (source / '.hidden').mkdir()
    (source / 'README.md').write_text('private contents', encoding='utf-8')
    endpoint = '/import/folders'
    assert client.post(endpoint, base_url=base, json={'path': str(source)}).status_code == 403
    response = client.post(endpoint, base_url=base,
        headers={'Origin': base, 'X-Setup-CSRF': csrf}, json={'path': str(source)})
    assert response.status_code == 200
    assert response.json['path'] == str(source.resolve())
    assert [row['name'] for row in response.json['folders']] == ['data']
    assert 'private contents' not in response.get_data(as_text=True)
    assert response.json['parent'] == str(tmp_path.resolve())
    assert not app.extensions['installation_state'].value.get('browser_source')
    missing = client.post(endpoint, base_url=base,
        headers={'Origin': base, 'X-Setup-CSRF': csrf}, json={'path': str(source / 'missing')})
    assert missing.status_code == 409
    assert missing.json['code'] == 'folder_unavailable'


def test_resumed_inventory_filters_old_ignored_rows(browser):
    app, client, base, csrf = browser
    state = app.extensions['installation_state']
    state.save(dict(state.value, browser_source=dict(kind='directory', root='unused', rows=[
        dict(id='7', path='README.md', bytes=5, format='md', count=None, status='ignored')])))
    page = client.get('/import/', base_url=base)
    assert page.status_code == 200
    assert b'README.md' not in page.data
    assert b'Select the old installation root' in page.data


def test_sqlite_folder_inventory_and_single_selection(browser, tmp_path):
    from storage.sqlite_store import initialize
    app, client, base, csrf = browser
    old = tmp_path / 'previous'
    folder = old / 'data' / 'private'
    folder.mkdir(parents=True)
    initialize(path=folder / 'old.sqlite3')
    (folder / 'notes.md').write_text('ignored')
    response = client.post('/import/discover', base_url=base, headers={'Origin': base},
        data={'csrf': csrf, 'source': str(old), 'kind': 'sqlite'})
    assert response.status_code == 303
    desc = app.extensions['installation_state'].value['browser_source']
    assert len(desc['rows']) == 1
    row = desc['rows'][0]
    assert row['path'] == 'data/private/old.sqlite3'
    assert row['status'] == 'supported'
    assert client.get('/import/preview/' + row['id'], base_url=base).status_code == 200
    response = client.post('/import/run', base_url=base, headers={'Origin': base},
        data={'csrf': csrf, 'selected': row['id']})
    assert response.status_code == 303
    assert app.extensions['installation_state'].value['browser_report']['database']


def test_empty_devices_has_actionable_report_in_both_modes(browser, tmp_path):
    app, client, base, csrf = browser
    old = tmp_path / 'previous'
    old.mkdir()
    (old / 'devices.yml').write_text('devices: []\n')
    client.post('/import/discover', base_url=base, headers={'Origin': base},
        data={'csrf': csrf, 'source': str(old), 'kind': 'directory'})
    for partial in ('0', '1'):
        response = client.post('/import/run', base_url=base, headers={'Origin': base},
            data={'csrf': csrf, 'selected': '0', 'allow_partial': partial})
        assert response.status_code == 303
        report = app.extensions['installation_state'].value['browser_report']
        assert report['database'] is None
        assert report['events'][0]['code'] == 'devices_empty'
    assert client.post('/abort', base_url=base, headers={'Origin': base},
        data={'csrf': csrf}).status_code == 303


@pytest.mark.parametrize('kind', ['directory', 'sqlite'])
def test_source_path_and_kind_survive_reload(browser, tmp_path, kind):
    from storage.sqlite_store import initialize
    from markupsafe import escape
    app, client, base, csrf = browser
    old = tmp_path / 'old & previous'
    old.mkdir()
    if kind == 'sqlite':
        initialize(path=old / 'bridge.sqlite3')
    response = client.post('/import/discover', base_url=base, headers={'Origin': base},
        data={'csrf': csrf, 'source': str(old), 'kind': kind})
    assert response.status_code == 303
    for _ in range(2):
        page = client.get('/import/', base_url=base).get_data(as_text=True)
        assert 'value="' + str(escape(str(old))) + '" required' in page
        assert 'value="' + kind + '" selected' in page
    assert app.extensions['installation_state'].value['source_input'] == {'path': str(old), 'kind': kind}
