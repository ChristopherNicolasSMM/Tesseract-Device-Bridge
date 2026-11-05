import json

from setup.doctor import inspect_installation


def test_doctor_clean_root_has_no_side_effects(tmp_path):
    root = tmp_path / 'not-created'
    result = inspect_installation(root)
    assert result['setup_status'] == 'new'
    assert result['issues'] == []
    assert not root.exists()


def test_doctor_never_returns_secrets_or_arbitrary_metadata(tmp_path):
    root = tmp_path / 'clone'
    private = root / 'data/private'
    private.mkdir(parents=True)
    (root / '.env').write_text('ADMIN_TOKEN=private-test-value', encoding='utf-8')
    receipt = private / 'installation.json'
    receipt.write_text(json.dumps({'version': 1, 'status': 'publishing',
                                   'password': 'private-test-value'}), encoding='utf-8')
    before = receipt.read_bytes()
    result = inspect_installation(root)
    assert result['issues'] == ['publication_incomplete']
    assert 'private-test-value' not in json.dumps(result)
    assert receipt.read_bytes() == before


def test_doctor_flags_inconsistent_published_state(tmp_path):
    root = tmp_path / 'clone'
    private = root / 'data/private'
    private.mkdir(parents=True)
    (private / 'installation.json').write_text(
        json.dumps({'version': 1, 'status': 'ready_simulated'}), encoding='utf-8')
    result = inspect_installation(root)
    assert 'published_file_missing' in result['issues']
    assert 'state_needs_recovery' in result['issues']
