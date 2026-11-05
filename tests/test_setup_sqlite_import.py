import sqlite3
from contextlib import closing
import pytest
from setup.state import InstallationState, SetupError
from setup.sqlite_import import import_sqlite, capture, inspect


def test_legacy_sqlite_source_unchanged(tmp_path):
    from storage.sqlite_store import initialize
    source = tmp_path / 'old.sqlite3'
    initialize(path=source)
    before = source.read_bytes()
    state = InstallationState(tmp_path / 'new')
    try:
        state.start('en')
        report = import_sqlite(state, source)
        assert report['source_kind'] == 'legacy'
        target = state.staging() / report['database']
        assert inspect(target) == ('orm', 'bridge_orm_0003')
        assert source.read_bytes() == before
        assert not report['runtime_authorized']
        state.abort()
        assert not target.exists()
    finally:
        state.close()


def test_empty_orm_import(tmp_path):
    from setup.bootstrap import bootstrap_empty
    old = InstallationState(tmp_path / 'old')
    new = InstallationState(tmp_path / 'new')
    try:
        old.start('en')
        source = bootstrap_empty(old)
        before = source.read_bytes()
        new.start('en')
        report = import_sqlite(new, source)
        assert report['source_kind'] == 'orm'
        assert report['needs_review']
        assert source.read_bytes() == before
    finally:
        old.close()
        new.close()


def test_unknown_sqlite_rejected(tmp_path):
    source = tmp_path / 'unknown.sqlite3'
    with closing(sqlite3.connect(source)) as conn:
        conn.execute('CREATE TABLE unknown(id INTEGER)')
        conn.commit()
    state = InstallationState(tmp_path / 'new')
    try:
        state.start('en')
        with pytest.raises(SetupError, match='Unrecognized'):
            import_sqlite(state, source)
    finally:
        state.close()


def test_wal_and_non_sqlite_rejected(tmp_path):
    from storage.sqlite_store import initialize
    source = tmp_path / 'old.sqlite3'
    initialize(path=source)
    sidecar = tmp_path / 'old.sqlite3-wal'
    sidecar.write_bytes(b'preserve')
    with pytest.raises(SetupError, match='sidecars'):
        capture(source, tmp_path / 'target.sqlite3')
    assert sidecar.read_bytes() == b'preserve'
    invalid = tmp_path / 'invalid'
    invalid.write_bytes(b'not sqlite')
    with pytest.raises(SetupError, match='Not a SQLite'):
        capture(invalid, tmp_path / 'target.sqlite3')
