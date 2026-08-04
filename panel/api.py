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

    Registra o valor como override manual (DeviceRuntime.set_manual_override)
    em vez de escrever cru — assim, se este device for uma bomba usada
    por uma receita ativa (pumps de um step), o RecipeEngine nunca
    sobrescreve o comando manual silenciosamente na próxima troca de
    etapa (ver _apply_pumps). Sem efeito colateral para atuadores fora
    de qualquer receita — a checagem só é consultada por _apply_pumps.
    """
    payload = request.get_json(silent=True) or {}
    if "value" not in payload:
        return jsonify({"error": "corpo da requisição deve conter 'value'."}), 400

    try:
        device = _runtime().get_device_config(device_id)
        if device.has_duty_control:
            return jsonify({
                "error": "device com controle de potência — use POST .../duty e .../duty/enabled."
            }), 400
        state = _runtime().set_manual_override(device_id, payload["value"])
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    except DeviceRuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(asdict(state))


@bp.post("/devices/<device_id>/duty")
def duty_device(device_id: str):
    """
    Define o VALOR de % configurado para o override manual de potência
    de um atuador com controle por time-proportioning
    (hardware.window_seconds no devices.yml) — NÃO liga o atuador
    sozinho. Só tem efeito físico quando o controle estiver armado via
    POST .../duty/enabled — ajustar o slider no painel não pode
    energizar a resistência sem uma ação explícita de ligar.

    Corpo: {"duty_percent": 40} (obrigatório, numérico 0-100).
    """
    payload = request.get_json(silent=True) or {}
    if "duty_percent" not in payload or payload["duty_percent"] is None:
        return jsonify({"error": "corpo da requisição deve conter 'duty_percent' numérico."}), 400

    try:
        state = _runtime().set_manual_duty_percent(device_id, payload["duty_percent"])
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    except DeviceRuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(asdict(state))


@bp.post("/devices/<device_id>/duty/enabled")
def duty_enabled_device(device_id: str):
    """
    Liga/desliga o interruptor mestre do override manual de potência —
    separado do valor de % (POST .../duty). Enquanto desligado, o
    atuador fica em 0% mesmo que um valor de % tenha sido configurado
    (a menos que uma receita ativa esteja controlando ele via PID,
    nesse caso o duty da receita continua valendo normalmente).

    Corpo: {"enabled": true} liga; {"enabled": false} desliga.
    """
    payload = request.get_json(silent=True) or {}
    if "enabled" not in payload:
        return jsonify({"error": "corpo da requisição deve conter 'enabled' (bool)."}), 400

    try:
        state = _runtime().set_manual_enabled(device_id, bool(payload["enabled"]))
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
    now = time.time()
    current_vessel = None
    current_duty = 0.0
    if state.status in ("ramping", "holding") and state.step_index < engine.recipe.step_count():
        current_vessel = engine.recipe.steps[state.step_index].vessel
        current_duty = engine.current_duty(current_vessel)
    return {
        "loaded_recipe_name": engine.recipe_name,
        "recipe_name": state.recipe_name,
        "status": state.status,
        "step_index": state.step_index,
        "step_started_at": state.step_started_at,
        "hold_started_at": state.hold_started_at,
        "hold_elapsed_seconds_at_pause": state.hold_elapsed_seconds_at_pause,
        "paused_from_status": state.paused_from_status,
        "current_vessel": current_vessel,
        "current_duty_percent": current_duty,
        "total_estimated_minutes": engine.total_estimated_minutes(),
        "total_elapsed_seconds": engine.total_elapsed_seconds(now),
        "pending_alarms": [asdict(a) for a in engine.pending_alarms],
    }


@bp.get("/recipe/status")
def recipe_status():
    engine = _recipe_engine()
    if engine is None:
        return jsonify({"error": "Nenhuma receita carregada neste bridge."}), 404
    return jsonify(_recipe_status_payload(engine))


@bp.get("/recipe/definition")
def recipe_definition():
    """
    Expõe a definição estática da receita carregada (vasilhas + etapas)
    — separado de /recipe/status (que é o estado de execução) porque a
    definição não muda em runtime; a UI carrega isso uma vez e só faz
    polling de /recipe/status + /devices para o estado dinâmico.
    """
    engine = _recipe_engine()
    if engine is None:
        return jsonify({"error": "Nenhuma receita carregada neste bridge."}), 404

    recipe = engine.recipe
    runtime = _runtime()
    return jsonify({
        "name": recipe.name,
        "vessel_order": recipe.ordered_vessel_names(),
        "vessels": {
            v.id: {
                "label": v.name,  # chave JSON mantida como "label" por retrocompatibilidade com o painel; valor vem de VesselConfig.name
                "heater_device_id": v.heater_device_id,
                "sensor_device_id": v.sensor_device_id,
                # Fonte de verdade é hardware.window_seconds do heater no
                # devices.yml (VesselConfig.window_seconds foi removido —
                # era um campo duplicado e obsoleto).
                "window_seconds": runtime.get_device_config(v.heater_device_id).hardware["window_seconds"],
                "order": v.order,
            }
            for v in recipe.vessels
        },
        "steps": [
            {
                "vessel": s.vessel,
                "target_temp": s.target_temp,
                "hold_minutes": s.hold_minutes,
                "pumps": s.pumps,
                "label": s.label,
            }
            for s in recipe.steps
        ],
    })


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


@bp.post("/recipe/pause")
def recipe_pause():
    """Pausa deliberada pelo usuário — desliga os atuadores (failsafe) e espera POST /recipe/resume."""
    engine = _recipe_engine()
    if engine is None:
        return jsonify({"error": "Nenhuma receita carregada neste bridge."}), 404
    try:
        engine.pause(now=time.time())
    except RecipeEngineError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(_recipe_status_payload(engine))


@bp.post("/recipe/skip_next")
def recipe_skip_next():
    """Força avanço pra próxima etapa, ignorando temperatura/tempo de patamar."""
    engine = _recipe_engine()
    if engine is None:
        return jsonify({"error": "Nenhuma receita carregada neste bridge."}), 404
    try:
        engine.skip_next(now=time.time())
    except RecipeEngineError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(_recipe_status_payload(engine))


@bp.post("/recipe/skip_previous")
def recipe_skip_previous():
    """Volta pra etapa anterior (reiniciando ela do zero); na primeira etapa, reinicia a atual."""
    engine = _recipe_engine()
    if engine is None:
        return jsonify({"error": "Nenhuma receita carregada neste bridge."}), 404
    try:
        engine.skip_previous(now=time.time())
    except RecipeEngineError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(_recipe_status_payload(engine))


@bp.post("/recipe/reset_step")
def recipe_reset_step():
    """Reinicia a etapa atual do zero, sem mudar de etapa."""
    engine = _recipe_engine()
    if engine is None:
        return jsonify({"error": "Nenhuma receita carregada neste bridge."}), 404
    try:
        engine.reset_current_step(now=time.time())
    except RecipeEngineError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(_recipe_status_payload(engine))


@bp.post("/recipe/alarms/<int:alarm_id>/ack")
def recipe_acknowledge_alarm(alarm_id: int):
    """Confirma (dispensa) um alarme pendente — para o som no painel."""
    engine = _recipe_engine()
    if engine is None:
        return jsonify({"error": "Nenhuma receita carregada neste bridge."}), 404
    engine.acknowledge_alarm(alarm_id)
    return jsonify(_recipe_status_payload(engine))
