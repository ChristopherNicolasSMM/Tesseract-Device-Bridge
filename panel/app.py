"""
Factory do painel manual (Flask).

create_panel_app() não sabe nada de MQTT — recebe um `mqtt_status_provider`
opcional (callable que retorna "connected"/"disconnected"/"disabled"/"unknown").
Quando chamado isoladamente (Fase 3, sem bridge.py), o status é sempre
derivado só do `config.mqtt.enabled`. Na Fase 4, bridge.py passa um
provider real ligado ao estado da conexão MQTT.
"""

from __future__ import annotations

from typing import Callable, Optional

from flask import Flask

from config import BridgeConfig
from device_runtime import DeviceRuntime
from panel.api import bp as api_bp


def default_status_provider(config: BridgeConfig) -> Callable[[], str]:
    def _provider() -> str:
        return "disabled" if not config.mqtt.enabled else "unknown"
    return _provider


def create_panel_app(
    config: BridgeConfig,
    runtime: DeviceRuntime,
    mqtt_status_provider: Optional[Callable[[], str]] = None,
) -> Flask:
    app = Flask(__name__)
    app.config["DEVICE_RUNTIME"] = runtime
    app.config["MQTT_STATUS_PROVIDER"] = mqtt_status_provider or default_status_provider(config)

    app.register_blueprint(api_bp)

    @app.get("/")
    def index():
        from flask import render_template
        return render_template("index.html")

    return app
