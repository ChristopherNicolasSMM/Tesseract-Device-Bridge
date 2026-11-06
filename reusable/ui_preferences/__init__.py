"""Optional browser-only layout preferences; no persistence or runtime backend."""


def register_layout(app):
    """Publish trusted assets and the control template once per host Flask app."""
    if 'layout_ui' in app.blueprints:
        return
    from flask import Blueprint
    app.register_blueprint(Blueprint('layout_ui', __name__, template_folder='templates',
        static_folder='static', static_url_path='/layout-assets'))
