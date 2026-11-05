import json
from pathlib import Path
import pytest
import yaml
from setup.state import InstallationState, SetupError
from setup.legacy import import_directory
from setup.uploads import capture_uploads, import_uploads


def source_config(tmp_path):
    from storage.sqlite_store import INITIAL_CONFIG
    source = tmp_path / 'old'
    source.mkdir()
    (source / 'devices.yml').write_text(yaml.safe_dump(INITIAL_CONFIG), encoding='utf-8')
    return source


def test_partial_bad_optional_file_is_reported(tmp_path):
    source = source_config(tmp_path)
    private = source / 'data/private'
    private.mkdir(parents=True)
    bad = private / 'sensor_calibration.json'
    bad.write_text('invalid JSON secret-value', encoding='utf-8')
    state = InstallationState(tmp_path / 'new')
    try:
        state.start('en')
        report = import_directory(state, source, allow_partial=True)
        assert report['needs_review']
        assert report['database']
        assert any(e['code'] == 'file_rejected' for e in report['events'])
        assert 'secret-value' not in json.dumps(report)
        assert bad.read_text(encoding='utf-8') == 'invalid JSON secret-value'
    finally:
        state.close()


def test_critical_invalid_devices_never_produces_database(tmp_path):
    source = tmp_path / 'old'
    source.mkdir()
    (source / 'devices.yml').write_text('devices: []', encoding='utf-8')
    state = InstallationState(tmp_path / 'new')
    try:
        state.start('en')
        report = import_directory(state, source, allow_partial=True)
        assert report['database'] is None
        assert report['status'] == 'needs_review'
        assert not report['runtime_authorized']
    finally:
        state.close()


def test_strict_failure_records_safe_error(tmp_path):
    source = tmp_path / 'old'
    source.mkdir()
    (source / 'devices.yml').write_text('devices: []', encoding='utf-8')
    state = InstallationState(tmp_path / 'new')
    try:
        state.start('en')
        with pytest.raises(Exception):
            import_directory(state, source)
        reports = list(state.staging().glob('failed-*/report.json'))
        assert reports
        report = json.loads(reports[0].read_text(encoding='utf-8'))
        assert report['events'][0]['category'] == 'blocking_error'
    finally:
        state.close()


def test_upload_traversal_and_roundtrip(tmp_path):
    from storage.sqlite_store import INITIAL_CONFIG
    state = InstallationState(tmp_path)
    try:
        state.start('en')
        with pytest.raises(SetupError):
            capture_uploads(state, {'../devices.yml': b'bad'})
        with pytest.raises(SetupError):
            capture_uploads(state, {'devices.yml': 'not bytes'})
        report = import_uploads(state, {'devices.yml': yaml.safe_dump(INITIAL_CONFIG).encode('utf-8')})
        assert report['database']
        assert not report['runtime_authorized']
        staging = state.staging()
        state.abort()
        assert not staging.exists()
    finally:
        state.close()
