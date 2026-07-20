"""
Roda o bridge completo: MQTT (status agregado + comandos + publicação
de sensores), painel manual opcional em paralelo (mesmo DeviceRuntime
compartilhado), e RecipeEngine opcional (motor de receita autônomo —
ver recipe_engine/) se um arquivo de receita existir.

Uso:
    python run_bridge.py [caminho/para/devices.yml] [caminho/para/recipe.yml]
    python run_bridge.py --debug   # ativa logs de nível DEBUG

Receita é opcional — se `recipe.yml` (ou o caminho passado) não
existir, o bridge roda normalmente sem motor de receita, exatamente
como antes desta funcionalidade existir.
"""

import logging
import sys
import threading
import time

# Logging colorido deve ser o primeiro import do projeto, antes de
# qualquer outro módulo que crie loggers (ou eles herdam o formatter
# padrão do Python em vez do nosso).
from logging_config import setup_logging
setup_logging(debug="--debug" in sys.argv)

from bridge import Bridge
from config import BridgeConfig
from device_runtime import DeviceRuntime
from gpio.simulated_backend import SimulatedGPIOBackend
from panel.app import create_panel_app
from recipe_engine.engine import RecipeEngine
from recipe_engine.models import Recipe, RecipeError
from run_panel import ensure_config_file

logger = logging.getLogger("tesseract_bridge.run_bridge")

DEFAULT_RECIPE_PATH = "recipe.yml"
DEFAULT_RECIPE_STATE_PATH = "recipe_state.json"


def mqtt_status_provider(bridge: Bridge, config: BridgeConfig):
    def _provider() -> str:
        if not config.mqtt.enabled:
            return "disabled"
        return bridge.status_handler.last_status or "unknown"
    return _provider


def load_recipe_engine(runtime: DeviceRuntime, config: BridgeConfig, recipe_path: str):
    """
    Carrega o motor de receita se `recipe_path` existir e for válido.
    Ausência do arquivo não é erro — motor de receita é opcional, o
    bridge funciona normalmente sem ele (caso de uso "só GPIO<->MQTT",
    sem automação de processo).
    """
    from pathlib import Path

    if not Path(recipe_path).exists():
        return None

    try:
        recipe = Recipe.load(recipe_path, config)
    except RecipeError as exc:
        logger.error("Receita em '%s' inválida, motor de receita desabilitado: %s", recipe_path, exc)
        return None

    engine = RecipeEngine(runtime, recipe, DEFAULT_RECIPE_STATE_PATH, now=time.time())
    if engine.state.status == "paused_after_crash":
        logger.warning(
            "Receita '%s' estava em execução quando o processo encerrou — "
            "failsafe já aplicado, aguardando confirmação manual (POST /api/recipe/resume) "
            "para retomar de onde parou.",
            recipe.name,
        )
    return engine


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "devices.yml"
    recipe_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_RECIPE_PATH

    ensure_config_file(config_path)
    config = BridgeConfig.load(config_path)

    if config.backend == "real":
        from gpio.real_backend import RealGPIOBackend  # implementado na Fase 5
        backend = RealGPIOBackend()
    else:
        backend = SimulatedGPIOBackend()

    runtime = DeviceRuntime(config, backend)
    recipe_engine = load_recipe_engine(runtime, config, recipe_path)
    bridge = Bridge(config, runtime, recipe_engine=recipe_engine)

    if config.panel.enabled:
        app = create_panel_app(config, runtime, mqtt_status_provider(bridge, config), recipe_engine=recipe_engine)
        panel_thread = threading.Thread(
            target=lambda: app.run(host=config.panel.host, port=config.panel.port, debug=False),
            daemon=True,
        )
        panel_thread.start()
        print(f"Painel disponível em http://{config.panel.host}:{config.panel.port}")

    if config.mqtt.enabled:
        print(f"Conectando ao broker MQTT em {config.mqtt.host}:{config.mqtt.port}...")
    else:
        print("mqtt.enabled=false — rodando só em modo painel manual.")

    if recipe_engine is not None:
        print(f"Motor de receita ativo (status atual: {recipe_engine.state.status}).")
    else:
        print(f"Nenhuma receita em '{recipe_path}' — rodando sem motor de receita.")

    bridge.run_forever()


if __name__ == "__main__":
    main()
