"""Optional Flask adapter; host controls published scope and read authorization."""
from io import BytesIO
import mimetypes

from .catalog import DocumentError
from .render import render_document


def register_documentation(app, library, *, url_prefix='/help', authorize=None, title='Ajuda e documentação',
                           home_links=(), layout_control=False):
    from flask import Blueprint, abort, g, jsonify, render_template, request, send_file, url_for
    from markupsafe import Markup
    from werkzeug.exceptions import HTTPException
    bp = Blueprint('documentation', __name__, template_folder='templates', static_folder='static',
                   static_url_path='/assets', url_prefix=url_prefix)

    @bp.before_request
    def permission():
        if authorize is not None:
            result = authorize()
            if result is False:
                abort(403)
            if result not in (None, True):
                return result

    @bp.after_request
    def headers(response):
        nonce = getattr(g, 'documentation_layout_nonce', None)
        script_policy = "script-src 'nonce-" + nonce + "'; " if nonce else "script-src 'none'; "
        response.headers.update({'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff',
            'Referrer-Policy':'no-referrer',
            'Content-Security-Policy':"default-src 'none'; " + script_policy + "style-src 'self'; img-src 'self'; form-action 'self'; frame-ancestors 'self'; base-uri 'none'"})
        return response

    @bp.errorhandler(Exception)
    def document_failure(exc):
        # Browsing a manual must never reach the host's runtime emergency handler.
        if isinstance(exc, HTTPException):
            return exc
        app.logger.warning('Documentation unavailable: %s', type(exc).__name__)
        return 'Documentação indisponível. Verifique a instalação dos recursos de ajuda.', 503

    @bp.get('/')
    def page():
        theme = request.args.get('theme', 'dark')
        theme = theme if theme in ('dark','light') else 'dark'
        embedded = request.args.get('embedded') == '1'
        nonce = None
        if layout_control and not embedded:
            import secrets
            nonce = secrets.token_urlsafe(24)
            g.documentation_layout_nonce = nonce
        query = request.args.get('q', '')[:160]
        category = request.args.get('category', '')[:80]
        documents = library.catalog()
        categories = sorted({d.category for d in documents})
        visible = [d for d in documents if not category or d.category == category]
        current, rendered = None, None
        document_id = request.args.get('doc')
        if document_id:
            try:
                current = library.document(document_id)
            except (DocumentError, OSError):
                abort(404)
            rendered = render_document(library, current,
                document_url=lambda path: url_for('documentation.page', doc=path, theme=theme, embedded='1' if embedded else None),
                asset_url=lambda path: url_for('documentation.asset', path=path))
            rendered = {k: Markup(v) for k,v in rendered.items()}
        return render_template('documentation/page.html', title=title, current=current, rendered=rendered,
            documents=visible, categories=categories, category=category, query=query, theme=theme,
            layout_enabled=layout_control, layout_nonce=nonce, embedded=embedded,
            results=library.search(query, visible) if query.strip() else [], home_links=home_links)

    @bp.get('/raw')
    def raw():
        document_id = request.args.get('doc', '')
        try:
            content = library.read_bytes(document_id)
        except (DocumentError, OSError):
            abort(404)
        return send_file(BytesIO(content), mimetype='text/plain', as_attachment=True,
                         download_name='documento.md')

    @bp.get('/image')
    def asset():
        document_id = request.args.get('path', '')
        try:
            content = library.read_bytes(document_id, asset=True)
        except (DocumentError, OSError):
            abort(404)
        return send_file(BytesIO(content), mimetype=mimetypes.guess_type(document_id)[0] or 'application/octet-stream')

    @bp.get('/catalog')
    def catalog():
        return jsonify(documents=[dict(path=d.path, title=d.title, category=d.category) for d in library.catalog()])

    app.register_blueprint(bp)
    return library
