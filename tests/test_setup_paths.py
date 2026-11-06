"""Compact-path compatibility and native Windows regression coverage."""
import os
import uuid
from pathlib import Path
import pytest
import yaml
from setup.state import InstallationState
from setup.legacy import import_directory
from reusable.guided_setup.paths import compact_attempt_name, require_staging_budget, PathLengthError


def test_compact_identity_preserves_uuid_and_uses_windows_safe_alphabet():
    import base64
    attempt = uuid.uuid4().hex
    name = compact_attempt_name(attempt)
    assert len(name) == 26
    assert set(name) <= set('abcdefghijklmnopqrstuvwxyz234567')
    assert base64.b32decode(name.upper() + '======').hex() == attempt


def test_windows_budget_accounts_for_journals_and_utf16(tmp_path):
    # The helper measures the full absolute directory, not only its basename.
    directory = tmp_path / ('x' * 260)
    with pytest.raises(PathLengthError) as error:
        require_staging_budget(directory, windows=True)
    assert error.value.code == 'setup_path_too_long'
    require_staging_budget(directory, windows=False)
    # Non-BMP characters consume two Windows UTF-16 path units each.
    unicode_directory = tmp_path / ('\U0001f600' * 100)
    with pytest.raises(PathLengthError):
        require_staging_budget(unicode_directory, windows=True)


def test_old_attempt_resumes_without_moving_candidates(tmp_path):
    state = InstallationState(tmp_path / 'clone')
    try:
        state.save(dict(version=1, status='in_progress', language='en', attempt='a' * 32))
        old = state.staging()
        assert old.name == 'attempt-' + 'a' * 32
        old.mkdir()
        candidate = old / 'candidate.tmp'
        candidate.write_text('preserve')
        state.start('en')
        assert state.staging() == old
        assert candidate.read_text() == 'preserve'
        state.abort()
        state.start('en')
        assert state.value['staging_layout'] == 'compact'
        assert len(state.staging().name) == 26
    finally:
        state.close()


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows MAX_PATH regression')
def test_windows_import_from_158_character_clone_root(tmp_path):
    from storage.sqlite_store import INITIAL_CONFIG
    # Match the root length inferred from the uploaded setup.18 diagnostic.
    padding = 158 - len(str(tmp_path)) - 1
    if padding < 1:
        pytest.skip('The pytest temporary parent itself exceeds the target root length')
    root = tmp_path / ('r' * padding)
    assert len(str(root)) == 158
    source = tmp_path / 'old'
    (source / 'data/private').mkdir(parents=True)
    (source / 'devices.yml').write_text(yaml.safe_dump(INITIAL_CONFIG), encoding='utf-8')
    (source / 'data/private/sensor_calibration.json').write_text('{"schema":1,"sensors":{}}', encoding='utf-8')
    state = InstallationState(root)
    try:
        state.start('en')
        report = import_directory(state, source)
        assert report['status'] == 'imported_staging'
        assert report['database']
        assert not report['runtime_authorized']
        target = state.staging() / report['database']
        assert target.is_file()
        assert all(len(str(p)) < 260 for p in state.staging().rglob('*'))
        state.abort()
        assert not target.exists()
    finally:
        state.close()
