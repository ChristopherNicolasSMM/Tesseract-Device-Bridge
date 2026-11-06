"""Configuration-only app for a zero-device ORM install. Never constructs runtime."""
import secrets
from flask import Flask, render_template

from config import BridgeConfig
from .admin_api import bp


def create_configuration_app(raw):
    app = Flask(__name__)
    app.secret_key = secrets.token_bytes(32)
    app.config.update(CONFIGURATION_ONLY=True, BRIDGE_CONFIG=BridgeConfig.from_dict(raw), DEVICE_RUNTIME=None,
                      RECIPE_ENGINE=None, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Strict',
                      SESSION_COOKIE_NAME='bridge_admin_' + str(raw['panel']['port']))
    app.register_blueprint(bp)
    from shared_ui.documentation import register_help
    register_help(app)

    @app.get('/')
    def index():
        return render_template('configuration.html')
    return app
