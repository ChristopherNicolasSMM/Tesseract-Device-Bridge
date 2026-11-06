"""Safe diagnostics and original-error preservation; no hardware involved."""
import json
import pytest
from setup.app import create_app
from setup.state import InstallationState
from setup.diagnostics import record, logger, checkpoint
from setup.reports import record_import, failure_report
from reusable.guided_setup.diagnostics import DiagnosticLog


def test_diagnostics_omit_secrets_and_keep_error_coordinates(tmp_path):
    state = InstallationState(tmp_path / 'clone')
    try:
        state.start('en')
        try:
            raise OSError(206, 'token=never-log-this', '/secret-user/credential.json')
        except OSError as exc:
            event_id = record(state, 'legacy.capture', 'error', exc=exc,
                              file_hint='data/public/devices.yml')
            report = failure_report('import_preparation_failed', exc, state=state)
        content = logger(state).read_all().decode('utf-8')
        assert 'never-log-this' not in content
        assert 'secret-user' not in content
        assert 'credential.json' not in content
        entry = json.loads(content.splitlines()[0])
        assert entry['event_id'] == event_id == report['diagnostic_id']
        assert entry['exception']['errno'] == 206
        assert entry['exception']['frames'][-1]['line'] > 0
        assert entry['file'] == 'data/public/devices.yml'
        state.abort()
        assert event_id in logger(state).read_all().decode('utf-8')
    finally:
        state.close()


def test_secondary_report_save_failure_does_not_hide_original(tmp_path, monkeypatch):
    import setup.reports as reports
    state = InstallationState(tmp_path / 'clone')
    state.start('en')
    original_error = OSError(206, 'secret-original-message')
    @record_import
    def broken(state):
        checkpoint(state, 'legacy.capture', file_hint='data/public/devices.yml')
        raise original_error
    def no_report(*args, **kwargs):
        raise OSError(13, 'secret-secondary-message')
    monkeypatch.setattr(reports.tempfile, 'mkdtemp', no_report)
    try:
        with pytest.raises(OSError) as caught:
            broken(state)
        assert caught.value is original_error
        entries = [json.loads(line) for line in logger(state).read_all().splitlines()]
        assert any(e['stage'] == 'legacy.capture' and e.get('exception', {}).get('errno') == 206 for e in entries)
        assert any(e['stage'] == 'report.persist' and e.get('exception', {}).get('errno') == 13 for e in entries)
        assert 'secret-' not in logger(state).read_all().decode('utf-8')
    finally:
        state.close()


def test_rotation_is_bounded_and_readable(tmp_path):
    directory = tmp_path / 'logs'
    log = DiagnosticLog(directory, project_root=tmp_path, build='test', max_bytes=1024, backups=2)
    for i in range(50):
        log.write('stage', 'completed')
    files = list(directory.iterdir())
    assert len(files) <= 3
    assert all(p.stat().st_size <= 1024 for p in files)
    for line in log.read_all().splitlines():
        assert json.loads(line)['build'] == 'test'


def test_download_is_local_and_available_before_start_and_after_abort(tmp_path):
    app = create_app(tmp_path / 'clone')
    base = 'http://127.0.0.1:8090'
    try:
        client = app.test_client()
        response = client.get('/diagnostics/download', base_url=base)
        assert response.status_code == 200
        assert 'attachment' in response.headers['Content-Disposition']
        assert response.headers['Cache-Control'] == 'no-store'
        assert json.loads(response.data.splitlines()[0])['stage'] == 'setup.start'
        assert client.get('/diagnostics/download', base_url=base,
                          environ_overrides={'REMOTE_ADDR': '192.0.2.1'}).status_code == 403
        page = client.get('/', base_url=base)
        assert b'/diagnostics/download' in page.data
    finally:
        app.extensions['installation_state'].close()


def test_logging_failure_cannot_replace_original_error(tmp_path, monkeypatch):
    state = InstallationState(tmp_path / 'clone')
    try:
        log = logger(state)
        def full(*args, **kwargs):
            raise OSError(28, 'disk full')
        monkeypatch.setattr(log, 'write', full)
        assert record(state, 'test', 'error', exc=ValueError('secret')) is None
    finally:
        state.close()
