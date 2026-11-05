from types import SimpleNamespace
import os
import pytest

from setup.state import SetupError
from setup.service import unit_quote


def test_unit_paths_are_quoted_and_specifiers_escaped():
    assert unit_quote('/path with space/100%/a$b') == '"/path with space/100%%/a$b"'
    assert unit_quote('/path/a$b', executable=True) == '"/path/a$$b"'
    with pytest.raises(SetupError):
        unit_quote('/path\nmalicious')


def test_service_unavailable_does_not_mutate_files(tmp_path, monkeypatch):
    from setup import service
    monkeypatch.setattr(service, 'compatible', lambda: False)
    fake = SimpleNamespace(root=tmp_path)
    with pytest.raises(SetupError):
        service.generate(fake)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(os.name == 'nt', reason='POSIX account database required')
def test_generated_service_is_unique_and_not_installed(tmp_path, monkeypatch):
    from setup import service, publication
    from setup.state import InstallationState
    state = InstallationState(tmp_path / 'new clone')
    try:
        state.start('en')
        receipt = {'id': 'a' * 32, 'status': 'ready_simulated'}
        monkeypatch.setattr(service, 'compatible', lambda: True)
        monkeypatch.setattr(publication, 'load_publication', lambda state: (receipt, None))
        import pwd
        monkeypatch.setattr(pwd, 'getpwnam', lambda user: SimpleNamespace(pw_gid=os.getgid(), pw_uid=1000))
        monkeypatch.setattr(service.os, 'getuid', lambda: 1000)
        unit = service.generate(state, 'bridgeuser')
        text = unit.read_text()
        assert 'User=bridgeuser' in text
        assert 'WantedBy=multi-user.target' in text
        assert 'graphical.target' not in text
        assert 'Environment=PYTHONUNBUFFERED=1' in text
        assert unit.name != 'tesseract-bridge.service'
        assert service.generate(state, 'bridgeuser') == unit
    finally:
        state.close()
