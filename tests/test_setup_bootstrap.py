import sqlite3
from contextlib import closing
import pytest
from setup.state import InstallationState, SetupError
from setup.bootstrap import bootstrap_empty


def test_empty_orm_bootstrap_and_retry(tmp_path):
    state = InstallationState(tmp_path)
    try:
        with pytest.raises(SetupError):
            bootstrap_empty(state)
        state.start('en')
        target = bootstrap_empty(state)
        original = target.read_bytes()
        assert bootstrap_empty(state) == target
        assert target.read_bytes() == original
        with closing(sqlite3.connect(target)) as conn:
            assert conn.execute('SELECT count(*) FROM bridge_control_profiles_v2').fetchone()[0] == 2
            assert not conn.execute("SELECT name FROM sqlite_master WHERE name='devices'").fetchall()
        assert not (tmp_path / '.env').exists()
        assert not (tmp_path / 'data/private/bridge.sqlite3').exists()
        state.abort()
        assert not target.exists()
    finally:
        state.close()
