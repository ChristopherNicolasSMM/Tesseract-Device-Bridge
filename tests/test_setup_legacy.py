from contextlib import closing
import sqlite3
import pytest
import yaml

from setup.state import InstallationState, SetupError
from setup.legacy import discover, import_directory


def test_yaml_only_source_preserved_and_normalized(tmp_path):
    from storage.sqlite_store import INITIAL_CONFIG
    source = tmp_path / 'old'
    source.mkdir()
    config = source / 'devices.yml'
    config.write_text(yaml.safe_dump(INITIAL_CONFIG), encoding='utf-8')
    (source / 'unknown.txt').write_text('never execute', encoding='utf-8')
    before = config.read_bytes()
    state = InstallationState(tmp_path / 'new')
    try:
        state.start('en')
        report = import_directory(state, source)
        assert config.read_bytes() == before
        assert report['runtime_authorized'] is False
        assert 'unknown.txt' in report['ignored']
        assert not any(e.get('file') == 'unknown.txt' for e in report['events'])
        target = state.staging() / report['database']
        with closing(sqlite3.connect(target)) as conn:
            assert conn.execute('SELECT count(*) FROM bridge_devices_v2').fetchone()[0] == 1
        state.abort()
        assert not target.exists()
        assert config.read_bytes() == before
    finally:
        state.close()


def test_selection_requires_devices_and_rejects_unknown(tmp_path):
    source = tmp_path / 'old'
    source.mkdir()
    (source / 'unknown.json').write_text('{}', encoding='utf-8')
    state = InstallationState(tmp_path / 'new')
    try:
        state.start('en')
        with pytest.raises(SetupError):
            import_directory(state, source, selected=['../escape'])
        with pytest.raises(SetupError):
            import_directory(state, source, selected=[])
        assert discover(source)[0]['status'] == 'ignored'
    finally:
        state.close()


def test_linked_files_are_rejected(tmp_path):
    source = tmp_path / 'old'
    source.mkdir()
    outside = tmp_path / 'outside'
    outside.write_text('secret', encoding='utf-8')
    try:
        (source / 'devices.yml').symlink_to(outside)
    except OSError:
        pytest.skip('Symlink privileges unavailable')
    with pytest.raises(SetupError):
        discover(source)


@pytest.mark.parametrize('partial', [False, True])
def test_main_reference_import_does_not_use_active_store(tmp_path, monkeypatch, partial):
    import shutil
    from pathlib import Path
    import control_settings
    source = tmp_path / 'old'
    shutil.copytree(Path(__file__).parent / 'fixtures/legacy_main', source)
    before = {p.relative_to(source): p.read_bytes() for p in source.rglob('*') if p.is_file()}
    def unavailable():
        raise RuntimeError('Operational DB is unavailable during setup')
    monkeypatch.setattr(control_settings, 'factory_settings', unavailable)
    state = InstallationState(tmp_path / 'new')
    try:
        state.start('en')
        report = import_directory(state, source, allow_partial=partial)
        assert report['status'] == 'imported_staging'
        assert not report['needs_review']
        assert not report['runtime_authorized']
        assert report['counts']['devices'] == 6
        assert report['counts']['recipes'] == 1
        with closing(sqlite3.connect(state.staging() / report['database'])) as conn:
            assert conn.execute('SELECT count(*) FROM bridge_devices_v2').fetchone()[0] == 6
            assert conn.execute('SELECT count(*) FROM bridge_recipes_v2').fetchone()[0] == 1
        assert before == {p.relative_to(source): p.read_bytes() for p in source.rglob('*') if p.is_file()}
    finally:
        state.close()


def test_conversion_failure_keeps_partial_warnings_without_exception_text(tmp_path, monkeypatch):
    from storage.sqlite_store import INITIAL_CONFIG
    import storage.orm_normalize
    source = tmp_path / 'old'
    (source / 'data/private').mkdir(parents=True)
    (source / 'devices.yml').write_text(yaml.safe_dump(INITIAL_CONFIG), encoding='utf-8')
    (source / 'data/private/sensor_calibration.json').write_text('invalid JSON', encoding='utf-8')
    def fail(**kwargs):
        raise storage.orm_normalize.NormalizationError('private-token-never-display')
    monkeypatch.setattr(storage.orm_normalize, 'normalize_copy', fail)
    state = InstallationState(tmp_path / 'new')
    try:
        state.start('en')
        report = import_directory(state, source, allow_partial=True)
        codes = [e['code'] for e in report['events']]
        assert 'file_rejected' in codes
        assert 'orm_conversion_failed' in codes
        assert 'import_mapping_error' in codes
        assert report['database'] is None
        assert not report['runtime_authorized']
        import json
        assert 'private-token' not in json.dumps(report)
    finally:
        state.close()


@pytest.mark.parametrize('topic', ['', '#', 'a/+', 'a\x00b', ' padded '])
def test_remote_topic_choice_rejects_invalid_topics(topic):
    import copy
    from storage.sqlite_store import INITIAL_CONFIG
    from storage.legacy_import import _normalize_legacy_config, LegacyImportError
    config = copy.deepcopy(INITIAL_CONFIG)
    config['devices'].append(dict(id='pump', name='Pump', role='actuator', subtype='digital',
        command_topic='pump/set', hardware={'pin': 19, 'remote_control': True}))
    with pytest.raises(LegacyImportError):
        _normalize_legacy_config(config, disable_invalid_remote_control=False,
                                 remote_state_topics={'pump': topic})
    assert config['devices'][-1]['hardware']['remote_control'] is True
    assert 'state_topic' not in config['devices'][-1]


def test_remote_resolution_rejects_unknown_devices_and_conflicting_choices():
    import copy
    from storage.sqlite_store import INITIAL_CONFIG
    from storage.legacy_import import _normalize_legacy_config, LegacyImportError
    config = copy.deepcopy(INITIAL_CONFIG)
    with pytest.raises(LegacyImportError):
        _normalize_legacy_config(config, disable_invalid_remote_control=False,
                                 remote_state_topics={'not_affected': 'actual/state'})
    with pytest.raises(LegacyImportError):
        _normalize_legacy_config(config, disable_invalid_remote_control=True,
                                 remote_state_topics={'not_affected': 'actual/state'})
