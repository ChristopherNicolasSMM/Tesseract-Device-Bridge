"""
Blueprint de API do painel manual.

Acesso direto a `DeviceRuntime`, sem passar por MQTT — é exatamente o
propósito do painel (seção 3.2 da spec): operar/testar hardware mesmo
sem broker nem Tesseract de pé.

Decisão de segurança registrada no README: sem autenticação na v1,
assume-se rede local confiável.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Callable, Optional

from flask import Blueprint, current_app, jsonify, request

from device_runtime import DeviceRuntime, DeviceRuntimeError

bp = Blueprint("panel_api", __name__, url_prefix="/api")


def _runtime() -> DeviceRuntime:
    return current_app.config["DEVICE_RUNTIME"]


def _mqtt_status_provider() -> Callable[[], str]:
    return current_app.config["MQTT_STATUS_PROVIDER"]


@bp.get("/status")
def get_status():
    provider = _mqtt_status_provider()
    return jsonify({"mqtt": provider()})


@bp.get("/devices")
def list_devices():
    states = _runtime().list_devices()
    return jsonify([asdict(s) for s in states])


@bp.get("/devices/<device_id>")
def get_device(device_id: str):
    try:
        state = _runtime().get_state(device_id)
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify(asdict(state))


@bp.post("/devices/<device_id>/command")
def command_device(device_id: str):
    """
    Aciona um atuador diretamente — equivalente ao que aconteceria se um
    comando chegasse via command_topic, mas sem depender do MQTT.
    """
    payload = request.get_json(silent=True) or {}
    if "value" not in payload:
        return jsonify({"error": "corpo da requisição deve conter 'value'."}), 400

    try:
        state = _runtime().set_actuator(device_id, payload["value"])
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    except DeviceRuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(asdict(state))


@bp.post("/devices/<device_id>/simulate")
def simulate_device(device_id: str):
    """
    Injeta um valor fake em um sensor — só funciona com backend
    simulado. Em backend real, inject() não existe no GPIOBackend
    (AttributeError), e isso é reportado como 400, não como erro 500
    genérico.
    """
    payload = request.get_json(silent=True) or {}
    if "value" not in payload:
        return jsonify({"error": "corpo da requisição deve conter 'value'."}), 400

    try:
        state = _runtime().inject_sensor(device_id, payload["value"])
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    except DeviceRuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    except AttributeError:
        return jsonify({
            "error": "Backend atual não suporta injeção manual de valor "
                     "(disponível apenas em backend='simulated')."
        }), 400
    return jsonify(asdict(state))
