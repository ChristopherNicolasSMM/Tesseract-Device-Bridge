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
