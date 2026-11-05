"""Static visual resources only; no dependency on panel, storage or hardware."""
from pathlib import Path


def register_ui(app):
    from flask import Blueprint
    from reusable import guided_setup
    blueprint = Blueprint('shared_ui', __name__, static_folder=str(Path(guided_setup.__file__).parent / 'static'),
                          static_url_path='/shared-ui')
    app.register_blueprint(blueprint)
