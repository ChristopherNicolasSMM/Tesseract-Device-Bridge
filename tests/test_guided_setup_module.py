"""Portable wizard contracts; all written files use a separate child directory."""
import json
import pytest
from flask import Flask, render_template
from reusable.guided_setup.configuration import ConfigurationError, host_name, port_number, update_env
from reusable.guided_setup.persistence import FileLock, LockError, atomic_json_write
from reusable.guided_setup.web import WizardStep, register_wizard_ui


def test_configuration_has_no_bridge_prefix_and_preserves_unrelated_lines():
    text = update_env('# keep\nAPP_PORT=10\nAPP_PORT=20\nSECRET="keep me"\n', {'APP_PORT': '8080'})
    assert text.count('APP_PORT=') == 1
    assert 'APP_PORT=8080\n' in text
    assert 'SECRET="keep me"' in text
    assert 'TESSERACT' not in text
    assert host_name('::1') == '::1'
    assert port_number('0080') == '80'
    with pytest.raises(ConfigurationError):
        update_env('', {'TOKEN': 'abc\nINJECT=1'})


def test_atomic_state_and_lock_in_arbitrary_project(tmp_path):
    directory = tmp_path / 'other-app'
    directory.mkdir()
    lock = FileLock(directory / 'installer.lock')
    try:
        with pytest.raises(LockError):
            FileLock(directory / 'installer.lock')
        atomic_json_write(directory / 'wizard.json', {'status': 'custom-stage'})
        assert json.loads((directory / 'wizard.json').read_text()) == {'status': 'custom-stage'}
        with pytest.raises(TypeError):
            atomic_json_write(directory / 'wizard.json', {'bad': object()})
        assert json.loads((directory / 'wizard.json').read_text()) == {'status': 'custom-stage'}
        assert not list(directory.glob('state-*.tmp'))
    finally:
        lock.close()
    reopened = FileLock(directory / 'installer.lock')
    reopened.close()


def test_reusable_layout_can_render_without_bridge_setup():
    app = Flask('another-project')
    register_wizard_ui(app, [WizardStep('network', '/network/', 'network')])
    labels = dict(title='Other project', security_note='Local', badge='Install', progress='Steps',
        network='Network', staging_only='Temporary', prepare='Configure', stop='Close', processing='Wait')
    @app.get('/network/')
    def page():
        return render_template('guided_setup/base.html', t=labels, language='en', theme='light', build='1')
    client = app.test_client()
    response = client.get('/network/')
    assert response.status_code == 200
    assert b'Other project' in response.data
    assert b'aria-current="step"' in response.data
    assert b'Tesseract' not in response.data
    assert client.get('/wizard-assets/wizard.css').status_code == 200
