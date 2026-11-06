"""Read-only documentation contracts; no GPIO, MQTT or schema migrations."""
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from flask import Flask
from reusable.documentation import DocumentLibrary, DocumentError
from reusable.documentation.render import render_document
from reusable.documentation.web import register_documentation


@pytest.fixture
def library(tmp_path):
    root = tmp_path / 'published'
    (root / 'docs/manual').mkdir(parents=True)
    (root / 'docs/technical').mkdir()
    (root / 'README.md').write_text('# Projeto\n[Manual](docs/manual/start.md)', encoding='utf-8')
    (root / 'docs/manual/start.md').write_text('# Instalação\n\n## Configuração\n\nBombas e sessão.\n\n[Arquitetura](../technical/core.md#limites)\n\n```python\nprint("exemplo")\n```\n\n| Nome | Valor |\n| --- | --- |\n| A | B |', encoding='utf-8')
    (root / 'docs/technical/core.md').write_text('# Arquitetura\n\n## Limites\nSem hardware.', encoding='utf-8')
    (root / '.env').write_text('SECRET=never-publish', encoding='utf-8')
    (root / 'private.md').write_text('never-publish', encoding='utf-8')
    return DocumentLibrary(root, categories=(('docs/manual/', 'Manuais'), ('docs/technical/', 'Técnica')))


def test_catalog_and_accent_insensitive_search(library):
    documents = library.catalog()
    assert len(documents) == 3
    assert [r['document'].path for r in library.search('instalacao configuracao', documents)] == ['docs/manual/start.md']
    assert not library.search('not-in-catalog')
    with pytest.raises(DocumentError):
        library.read_bytes('private.md')
    with pytest.raises(DocumentError):
        library.read_bytes('docs/../.env')
    with pytest.raises(DocumentError):
        library.read_bytes('docs\\manual\\start.md')


def test_catalog_limits_and_symlinks(library, tmp_path):
    outside = tmp_path / 'outside.md'
    outside.write_text('never-publish')
    link = library.root / 'docs/link.md'
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip('Symlink creation unavailable')
    assert all(d.path != 'docs/link.md' for d in library.catalog())
    with pytest.raises(DocumentError):
        library.read_bytes('docs/link.md')
    library.max_bytes = 8
    with pytest.raises(DocumentError):
        library.document('docs/manual/start.md')


def test_markdown_links_tables_and_xss_sanitization(library):
    path = library.root / 'docs/manual/start.md'
    path.write_text(path.read_text(encoding='utf-8') + '\n<script>alert(1)</script>\n<a href="javascript:alert(1)">unsafe</a>\n<img src="https://external.example/track.png" onerror="alert(1)">\n[Secret](../../.env)', encoding='utf-8')
    result = render_document(library, library.document('docs/manual/start.md'),
        document_url=lambda p: '/help/?doc=' + p,
        asset_url=lambda p: '/help/image?path=' + p)
    assert '<table>' in result['html']
    assert '<pre><code' in result['html']
    assert '/help/?doc=docs/technical/core.md#limites' in result['html']
    assert '#configuracao' in result['toc']
    assert '<script' not in result['html']
    assert 'onerror' not in result['html']
    assert 'javascript:' not in result['html']
    assert 'external.example' not in result['html']
    assert 'href="../../.env"' not in result['html']


def test_web_is_read_only_and_blocks_unpublished_files(library):
    app = Flask(__name__)
    register_documentation(app, library)
    client = app.test_client()
    assert client.get('/help/').status_code == 200
    response = client.get('/help/', query_string={'doc':'docs/manual/start.md'})
    assert response.status_code == 200
    assert b'<table>' in response.data
    assert "default-src 'none'" in response.headers['Content-Security-Policy']
    assert client.get('/help/raw', query_string={'doc':'.env'}).status_code == 404
    assert client.get('/help/', query_string={'doc':'private.md'}).status_code == 404
    assert client.get('/help/image', query_string={'path':'docs/technical/core.md'}).status_code == 404
    assert client.post('/help/').status_code == 405
    assert len(client.get('/help/catalog').json['documents']) == 3
    search = client.get('/help/', query_string={'q':'never-publish'})
    assert b'SECRET=never-publish' not in search.data
    assert b'Nenhum documento encontrado' in search.data


def test_host_authorization_applies_to_catalog_raw_and_assets(library):
    app = Flask(__name__)
    register_documentation(app, library, authorize=lambda: False)
    client = app.test_client()
    for path in ['/help/', '/help/catalog', '/help/raw?doc=README.md', '/help/assets/documentation.css']:
        assert client.get(path).status_code == 403


def test_document_failure_never_trips_runtime(library, monkeypatch):
    from config import BridgeConfig
    from storage.sqlite_store import INITIAL_CONFIG
    from panel.app import create_panel_app
    import reusable.documentation.web as web
    runtime = MagicMock()
    runtime.emergency_reason = None
    app = create_panel_app(BridgeConfig.from_dict(INITIAL_CONFIG), runtime)
    def broken(*args, **kwargs):
        raise RuntimeError('private-value-never-display')
    monkeypatch.setattr(web, 'render_document', broken)
    response = app.test_client().get('/help/', query_string={'doc':'docs/README.md'})
    assert response.status_code == 503
    assert b'private-value-never-display' not in response.data
    runtime.trip.assert_not_called()
    assert b'data-tab="help"' in app.test_client().get('/').data


def test_local_images_and_external_links(library):
    # Image bytes are never interpreted as HTML and only image suffixes are served.
    image = library.root / 'docs/manual/image.png'
    image.write_bytes(b'\x89PNG\r\n\x1a\n')
    source = library.root / 'docs/manual/images.md'
    source.write_text('# Images\n![Local](image.png)\n[External](https://example.org/manual)', encoding='utf-8')
    result = render_document(library, library.document('docs/manual/images.md'),
        document_url=lambda p:'/help/?doc=' + p, asset_url=lambda p:'/help/image?path=' + p)
    assert '/help/image?path=docs/manual/image.png' in result['html']
    assert 'rel="noopener noreferrer"' in result['html']
