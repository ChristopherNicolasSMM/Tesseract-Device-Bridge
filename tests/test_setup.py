"""Installation lifecycle and HTTP boundary; no operational hardware involved."""
import json
import os
import socket
import subprocess
import sys
import shutil
import time
import urllib.request
from pathlib import Path

import pytest

from setup.app import create_app
from setup.state import InstallationState, SetupError


@pytest.fixture
def wizard(tmp_path):
    root = tmp_path / "clean"
    app = create_app(root)
    app.config["TESTING"] = True
    yield app, root
    app.extensions["installation_state"].close()


def post(client, path, **data):
    client.get("/", base_url="http://127.0.0.1:8090")
    with client.session_transaction(base_url="http://127.0.0.1:8090") as session:
        data["csrf"] = session["csrf"]
    return client.post(path, data=data, base_url="http://127.0.0.1:8090",
                       headers={"Origin": "http://127.0.0.1:8090"})


def test_clean_boot_and_language(wizard):
    app, root = wizard
    client = app.test_client()
    response = client.get("/", base_url="http://127.0.0.1:8090")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert not (root / ".env").exists()
    assert not list(root.rglob("*.sqlite3"))
    assert post(client, "/start", language="en").status_code == 303
    assert b"Installation in progress" in client.get("/", base_url="http://127.0.0.1:8090").data


def test_resume_and_abort_preserve_foreign_files(tmp_path):
    root = tmp_path / "clone"
    state = InstallationState(root)
    state.start("en")
    attempt = state.value["attempt"]
    (state.staging() / "owned.tmp").write_text("temporary")
    foreign = state.directory / "unrelated.sqlite3"
    foreign.write_bytes(b"keep")
    state.close()
    state = InstallationState(root)
    try:
        state.start("pt_BR")
        assert state.value["attempt"] == attempt
        staging = state.staging()
        state.abort()
        assert not staging.exists()
        assert foreign.read_bytes() == b"keep"
        state.abort()
        assert state.value["status"] == "new"
    finally:
        state.close()


def test_exclusive_lock(tmp_path):
    first = InstallationState(tmp_path)
    try:
        with pytest.raises(SetupError, match="Another"):
            InstallationState(tmp_path)
    finally:
        first.close()
    InstallationState(tmp_path).close()


@pytest.mark.parametrize("headers,remote,host", [
    ({}, "10.0.0.2", "127.0.0.1:8090"),
    ({"X-Forwarded-For": "127.0.0.1"}, "10.0.0.2", "127.0.0.1:8090"),
    ({}, "127.0.0.1", "evil.example:8090"),
])
def test_network_boundary(wizard, headers, remote, host):
    client = wizard[0].test_client()
    assert client.get("/", base_url="http://" + host, headers=headers,
                      environ_overrides={"REMOTE_ADDR": remote}).status_code == 403


def test_csrf_origin_and_validation(wizard):
    client = wizard[0].test_client()
    assert client.post("/start", base_url="http://127.0.0.1:8090").status_code == 403
    client.get("/", base_url="http://127.0.0.1:8090")
    with client.session_transaction(base_url="http://127.0.0.1:8090") as session:
        csrf = session["csrf"]
    assert client.post("/start", data={"csrf": csrf, "language": "en"},
                       base_url="http://127.0.0.1:8090",
                       headers={"Origin": "http://evil.example"}).status_code == 403
    assert post(client, "/start", language="unsupported").status_code == 409
    assert post(client, "/abort").status_code == 303


@pytest.mark.parametrize("host,remote", [
    ("localhost:8090", "127.0.0.1"),
    ("127.0.0.1:8090", "::ffff:127.0.0.1"),
    ("[::1]:8090", "::1"),
])
def test_local_browser_aliases(wizard, host, remote):
    client = wizard[0].test_client()
    base = "http://" + host
    assert client.get("/", base_url=base,
                      environ_overrides={"REMOTE_ADDR": remote}).status_code == 200
    with client.session_transaction(base_url=base) as session:
        csrf = session["csrf"]
    assert client.post("/start", base_url=base, data={"language": "en", "csrf": csrf},
                       headers={"Origin": base},
                       environ_overrides={"REMOTE_ADDR": remote}).status_code == 303


def test_remote_ipv4_mapped_address_is_denied(wizard):
    assert wizard[0].test_client().get("/", base_url="http://127.0.0.1:8090",
        environ_overrides={"REMOTE_ADDR": "::ffff:10.0.0.2"}).status_code == 403


def test_state_corruption_fails_closed(tmp_path):
    state = InstallationState(tmp_path)
    state.save({"version": 999})
    state.close()
    with pytest.raises(SetupError):
        InstallationState(tmp_path)
    assert json.loads((tmp_path / "data/private/setup/state.json").read_text())["version"] == 999


@pytest.mark.skipif(os.name == "nt", reason="Symlinks require additional Windows privileges")
def test_staging_symlink_is_never_deleted(tmp_path):
    state = InstallationState(tmp_path / "clone")
    try:
        state.start("en")
        path = state.staging()
        path.rmdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "keep").write_text("keep")
        path.symlink_to(outside, target_is_directory=True)
        with pytest.raises(SetupError):
            state.abort()
        assert (outside / "keep").read_text() == "keep"
    finally:
        state.close()


def test_permission_failure_keeps_previous_state(tmp_path, monkeypatch):
    state = InstallationState(tmp_path)
    try:
        state.start("en")
        previous = (state.directory / "state.json").read_bytes()
        def denied(*args):
            raise PermissionError("denied")
        monkeypatch.setattr(os, "replace", denied)
        with pytest.raises(PermissionError):
            state.start("pt_BR")
        assert (state.directory / "state.json").read_bytes() == previous
    finally:
        state.close()


def test_cli_help_and_occupied_port():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-m", "setup", "--help"], cwd=root,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        result = subprocess.run([sys.executable, "-m", "setup", "--port",
                                 str(listener.getsockname()[1])], cwd=root,
                                capture_output=True, text=True, timeout=15)
    assert result.returncode != 0


def test_import_boundary_in_fresh_process(tmp_path):
    root = Path(__file__).resolve().parents[1]
    script = '''
import importlib.abc, sys
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'gpio', 'gpiozero', 'paho', 'device_runtime', 'panel', 'bridge', 'run_bridge', 'storage'}:
            raise AssertionError('Operational import: ' + fullname)
sys.meta_path.insert(0, Guard())
from setup.app import create_app
app = create_app(sys.argv[1])
assert app.test_client().get('/', base_url='http://127.0.0.1:8090').status_code == 200
app.extensions['installation_state'].close()
'''
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path / "fresh")],
                            cwd=root, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_actual_cli_in_clean_clone(tmp_path):
    root = Path(__file__).resolve().parents[1]
    clean = tmp_path / "clone"
    # Include the extracted toolkit, while omitting runtime/storage/hardware packages.
    for package in ("setup", "shared_ui", "reusable"):
        shutil.copytree(root / package, clean / package,
                        ignore=shutil.ignore_patterns("__pycache__"))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    process = subprocess.Popen([sys.executable, "-m", "setup", "--port", str(port)],
                               cwd=clean, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen("http://127.0.0.1:" + str(port), timeout=0.3) as response:
                    assert response.status == 200
                    break
            except OSError:
                if process.poll() is not None:
                    pytest.fail(process.communicate()[1].decode())
                time.sleep(0.03)
        else:
            pytest.fail("Setup did not answer HTTP requests")
        # Exercise resource delivery in the subprocess, not just imports/test_client.
        for path, expected in (
                ("/wizard-assets/wizard.css", b".setup-page"),
                ("/wizard-assets/theme.css", b"color-scheme"),
                ("/shared-ui/theme.css", b"color-scheme"),
                ("/static/setup.css", b"Project-specific overrides")):
            with urllib.request.urlopen("http://127.0.0.1:" + str(port) + path, timeout=2) as asset:
                assert asset.status == 200
                assert expected in asset.read()
        assert not (clean / ".env").exists()
        assert not list(clean.rglob("*.sqlite3"))
    finally:
        process.terminate()
        process.communicate(timeout=10)


def test_abort_busy_preserves_attempt_for_retry(tmp_path, monkeypatch):
    import shutil
    state = InstallationState(tmp_path / 'clone')
    try:
        state.start('en')
        original = shutil.rmtree
        def busy(path, **kwargs):
            raise PermissionError('locked')
        monkeypatch.setattr(shutil, 'rmtree', busy)
        with pytest.raises(SetupError) as error:
            state.abort()
        assert error.value.code == 'abort_files_busy'
        assert state.value['status'] == 'in_progress'
        monkeypatch.setattr(shutil, 'rmtree', original)
        state.abort()
        assert state.value['status'] == 'new'
    finally:
        state.close()


def test_abort_http_explains_publication_and_preserves_everything(wizard):
    app, root = wizard
    client = app.test_client()
    state = app.extensions['installation_state']
    # Start through the existing HTTP boundary, using the fixture's session.
    post(client, '/start', language='en')
    temporary = state.staging() / 'keep.tmp'
    temporary.write_text('temporary', encoding='utf-8')
    receipt = state.root / 'data/private/installation.json'
    receipt.write_text('{}', encoding='utf-8')
    response = post(client, '/abort')
    assert response.status_code == 409
    assert response.json['code'] == 'abort_publication_exists'
    assert receipt.read_text(encoding='utf-8') == '{}'
    assert temporary.read_text(encoding='utf-8') == 'temporary'


def test_abort_cleans_readonly_temp_and_keeps_foreign_files(tmp_path):
    import stat
    state = InstallationState(tmp_path / 'new')
    try:
        state.start('en')
        path = state.staging()
        temporary = path / 'readonly.tmp'
        temporary.write_text('temporary', encoding='utf-8')
        temporary.chmod(stat.S_IREAD)
        foreign = state.directory / 'foreign.tmp'
        foreign.write_text('keep', encoding='utf-8')
        state.abort()
        assert not path.exists()
        assert foreign.read_text(encoding='utf-8') == 'keep'
        assert state.value['status'] == 'new'
    finally:
        state.close()


def test_abort_http_busy_diagnostic_is_relative_and_retryable(wizard, monkeypatch):
    from reusable.guided_setup import cleanup
    app, root = wizard
    client = app.test_client()
    post(client, '/start', language='en')
    state = app.extensions['installation_state']
    temporary = state.staging() / 'captured.sqlite3'
    temporary.write_bytes(b'keep until unlocked')
    original = cleanup.remove_staging_tree
    def locked(path):
        raise PermissionError(13, 'secret exception text', str(temporary))
    monkeypatch.setattr(cleanup, 'remove_staging_tree', locked)
    response = post(client, '/abort')
    assert response.status_code == 409
    assert response.json['code'] == 'abort_files_busy'
    assert response.json['details'] == {'file': 'captured.sqlite3', 'os_error': 13}
    assert str(root) not in response.get_data(as_text=True)
    assert 'secret exception text' not in response.get_data(as_text=True)
    assert state.value['status'] == 'in_progress'
    monkeypatch.setattr(cleanup, 'remove_staging_tree', original)
    assert post(client, '/abort').status_code == 303
    assert state.value['status'] == 'new'


def test_readonly_cleanup_retries_owned_delete_only(tmp_path, monkeypatch):
    from reusable.guided_setup import cleanup
    import os
    root = tmp_path / 'owned'
    root.mkdir()
    owned = root / 'temp.tmp'
    owned.write_text('temporary')
    outside = tmp_path / 'outside.tmp'
    outside.write_text('keep')
    original = cleanup.shutil.rmtree
    def simulate_readonly(path, *, onerror):
        error = PermissionError(13, 'read only', str(owned))
        onerror(os.unlink, str(owned), (PermissionError, error, None))
        assert not owned.exists()
        with pytest.raises(PermissionError):
            onerror(os.unlink, str(outside), (PermissionError, error, None))
        original(path)
    monkeypatch.setattr(cleanup.shutil, 'rmtree', simulate_readonly)
    cleanup.remove_staging_tree(root)
    assert not root.exists()
    assert outside.read_text() == 'keep'
