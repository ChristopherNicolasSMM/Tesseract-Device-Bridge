import json
import sqlite3
from contextlib import closing

import pytest

from setup.state import InstallationState, SetupError
from setup.bootstrap import bootstrap_empty
from setup.infrastructure import prepare, DEFAULTS
from setup.security import prepare_security
from setup.publication import publish, recover, rollback, PublicationError, FINAL_DB, RECEIPT
from tesseract_bridge.infrastructure.installation import check_runtime


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    from setup import infrastructure
    monkeypatch.setattr(infrastructure, 'probe_port', lambda *args: 'infra_port_available')
    state = InstallationState(tmp_path / 'new')
    state.start('en')
    bootstrap_empty(state)
    prepare(state, DEFAULTS)
    prepare_security(state, 'none')
    yield state
    state.close()


def test_empty_installation_publishes_and_restarts_without_fake_devices(prepared):
    state = prepared
    receipt = publish(state, 'bridge.sqlite3')
    assert receipt['status'] == 'ready_simulated'
    assert (state.root / FINAL_DB).is_file()
    assert (state.root / '.env').is_file()
    check_runtime(state.root / FINAL_DB, root=state.root, simulated=True)
    with pytest.raises(RuntimeError):
        check_runtime(state.root / FINAL_DB, root=state.root, simulated=False)
    with closing(sqlite3.connect(state.root / FINAL_DB)) as conn:
        assert conn.execute('SELECT count(*) FROM bridge_devices_v2').fetchone()[0] == 0
    with pytest.raises(SetupError):
        state.abort()
    with pytest.raises(PublicationError):
        publish(state, 'bridge.sqlite3')
    root = state.root
    state.close()
    reopened = InstallationState(root)
    try:
        assert reopened.value['status'] == 'ready_simulated'
    finally:
        reopened.close()


def test_interrupted_publication_is_blocked_then_recovered(prepared, monkeypatch):
    from setup import publication
    original = publication._publish_env
    def fail(*args):
        raise PermissionError('injected interruption')
    monkeypatch.setattr(publication, '_publish_env', fail)
    with pytest.raises(PermissionError):
        publish(prepared, 'bridge.sqlite3')
    assert json.loads((prepared.root / RECEIPT).read_text())['status'] == 'publishing'
    with pytest.raises(RuntimeError):
        check_runtime(prepared.root / FINAL_DB, root=prepared.root, simulated=True)
    with pytest.raises(SetupError):
        prepared.abort()
    monkeypatch.setattr(publication, '_publish_env', original)
    assert recover(prepared)['status'] == 'ready_simulated'


def test_incomplete_publication_can_be_rolled_back(prepared, monkeypatch):
    from setup import publication
    monkeypatch.setattr(publication, '_publish_env', lambda *args: (_ for _ in ()).throw(PermissionError()))
    with pytest.raises(PermissionError):
        publish(prepared, 'bridge.sqlite3')
    rollback(prepared)
    assert not (prepared.root / FINAL_DB).exists()
    assert not (prepared.root / '.env').exists()
    assert not (prepared.root / RECEIPT).exists()
    assert (prepared.staging() / 'bridge.sqlite3').exists()


def test_existing_database_is_never_overwritten(prepared):
    target = prepared.root / FINAL_DB
    target.write_bytes(b'original')
    with pytest.raises(PublicationError):
        publish(prepared, 'bridge.sqlite3')
    assert target.read_bytes() == b'original'


def test_existing_env_requires_consent_and_is_preserved_in_backup(prepared):
    state = prepared
    original = '# Keep my env\nCUSTOM=original\n'
    (state.root / '.env').write_text(original, encoding='utf-8')
    prepare(state, DEFAULTS)
    prepare_security(state, 'none')
    with pytest.raises(PublicationError, match='publish_replace_env'):
        publish(state, 'bridge.sqlite3')
    receipt = publish(state, 'bridge.sqlite3', replace_env=True)
    assert (state.root / receipt['job'] / 'previous.env').read_text(encoding='utf-8') == original


def test_env_change_after_preparation_is_rejected(prepared):
    (prepared.root / '.env').write_text('CUSTOM=new', encoding='utf-8')
    with pytest.raises(PublicationError, match='publish_env_changed'):
        publish(prepared, 'bridge.sqlite3', replace_env=True)
    assert not (prepared.root / FINAL_DB).exists()


def test_configured_mode_unlocked_only_after_publication(prepared, tmp_path):
    from storage.sqlite_store import initialize
    from storage.orm_normalize import normalize_copy
    from setup.reports import save_report
    state = prepared
    old = tmp_path / 'old.sqlite3'
    initialize(path=old)
    job = state.staging() / 'import-test'
    job.mkdir()
    normalize_copy(source=old, destination=job / 'bridge.sqlite3')
    save_report(job, {'status': 'imported_staging', 'database': 'import-test/bridge.sqlite3',
                      'needs_review': False})
    prepare(state, dict(DEFAULTS, SIMULATION_ONLY='0'))
    prepare_security(state, 'none')
    with pytest.raises(PublicationError, match='publish_authorize'):
        publish(state, 'import-test/bridge.sqlite3')
    receipt = publish(state, 'import-test/bridge.sqlite3', authorize_real=True)
    assert receipt['status'] == 'ready_operational'
    # No runtime/GPIO is constructed. The stored backend in this fixture is simulated.
    check_runtime(state.root / FINAL_DB, root=state.root, simulated=False)


def test_database_replacement_is_detected(prepared):
    publish(prepared, 'bridge.sqlite3')
    with closing(sqlite3.connect(prepared.root / FINAL_DB)) as conn:
        conn.execute('PRAGMA application_id=0')
        conn.commit()
    with pytest.raises(RuntimeError, match='Identidade'):
        check_runtime(prepared.root / FINAL_DB, root=prepared.root, simulated=True)


def test_empty_published_app_exposes_admin_without_runtime(prepared, monkeypatch):
    from storage import store_router
    from storage.launch_config import configuration_only
    import storage.launch_config as launch
    from tesseract_bridge.infrastructure import installation
    publish(prepared, 'bridge.sqlite3')
    monkeypatch.setattr(installation, 'PROJECT_ROOT', prepared.root)
    monkeypatch.setattr(launch, 'load_infra_env', lambda: False)
    monkeypatch.setenv('TESSERACT_BRIDGE_DB', str(prepared.root / FINAL_DB))
    monkeypatch.setenv('TESSERACT_BRIDGE_STORAGE_MODE', 'orm')
    monkeypatch.setenv('TESSERACT_BRIDGE_SIMULATION_ONLY', '1')
    monkeypatch.setenv('TESSERACT_BRIDGE_LOCAL_ADMIN', '1')
    monkeypatch.setenv('TESSERACT_BRIDGE_ADMIN_TOKEN', '')
    app, port = configuration_only()
    assert app.config['DEVICE_RUNTIME'] is None
    base = 'http://127.0.0.1:' + str(port)
    response = app.test_client().get('/api/admin/config', base_url=base)
    assert response.status_code == 200
    assert response.json['config']['devices'] == []
    with pytest.raises(Exception):
        store_router.load_config()
