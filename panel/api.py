"""
Blueprint de API do painel manual.

Acesso direto a `DeviceRuntime`, sem passar por MQTT — é exatamente o
propósito do painel (seção 3.2 da spec): operar/testar hardware mesmo
sem broker nem Tesseract de pé.

Decisão de segurança registrada no README: sem autenticação na v1,
assume-se rede local confiável.

Endpoints de receita (/api/recipe/*) usam time.time() diretamente —
única exceção à convenção de "now explícito" do resto do código, já
que esta é a fronteira de I/O real (requisição HTTP do usuário), não
lógica pura testável.
"""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Callable, Optional

from flask import Blueprint, current_app, jsonify, request

from device_runtime import DeviceRuntime, DeviceRuntimeError
from recipe_engine.engine import RecipeEngine, RecipeEngineError

bp = Blueprint("panel_api", __name__, url_prefix="/api")


def _runtime() -> DeviceRuntime:
    return current_app.config["DEVICE_RUNTIME"]


def _mqtt_status_provider() -> Callable[[], str]:
    return current_app.config["MQTT_STATUS_PROVIDER"]


def _recipe_engine() -> Optional[RecipeEngine]:
    return current_app.config.get("RECIPE_ENGINE")


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


def _recipe_status_payload(engine: RecipeEngine) -> dict:
    state = engine.state
    return {
        "loaded_recipe_name": engine.recipe_name,
        "recipe_name": state.recipe_name,
        "status": state.status,
        "step_index": state.step_index,
        "step_started_at": state.step_started_at,
        "hold_started_at": state.hold_started_at,
        "hold_elapsed_seconds_at_pause": state.hold_elapsed_seconds_at_pause,
        "paused_from_status": state.paused_from_status,
    }


@bp.get("/recipe/status")
def recipe_status():
    engine = _recipe_engine()
    if engine is None:
        return jsonify({"error": "Nenhuma receita carregada neste bridge."}), 404
    return jsonify(_recipe_status_payload(engine))


@bp.post("/recipe/start")
def recipe_start():
    engine = _recipe_engine()
    if engine is None:
        return jsonify({"error": "Nenhuma receita carregada neste bridge."}), 404
    engine.start(now=time.time())
    return jsonify(_recipe_status_payload(engine))


@bp.post("/recipe/abort")
def recipe_abort():
    engine = _recipe_engine()
    if engine is None:
        return jsonify({"error": "Nenhuma receita carregada neste bridge."}), 404
    engine.abort(now=time.time())
    return jsonify(_recipe_status_payload(engine))


@bp.post("/recipe/resume")
def recipe_resume():
    engine = _recipe_engine()
    if engine is None:
        return jsonify({"error": "Nenhuma receita carregada neste bridge."}), 404
    try:
        engine.resume(now=time.time())
    except RecipeEngineError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(_recipe_status_payload(engine))
