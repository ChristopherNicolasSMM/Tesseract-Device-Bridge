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

# ===========================================================================
# BOOT LOG — deve ser a PRIMEIRA coisa que roda, antes de qualquer import.
#
# Por quê: quando o processo sobe via systemd (sem terminal interativo),
# qualquer falha de importação silencia tudo — o serviço marca "failed"
# mas o motivo não aparece claramente no journal. O boot.log resolve isso:
# ele grava em disco ANTES de tentar importar flask, paho, etc., então se
# travar no meio dos imports você sabe exatamente onde parou.
#
# Localização: /var/log/tesseract-bridge/boot.log
# Fallback: ./logs/boot.log (se não tiver permissão em /var/log)
# ===========================================================================
import os
import sys
import datetime

def _boot_log(msg: str) -> None:
    """
    Grava uma linha no arquivo de boot log, independente do logging
    Python normal. Nunca levanta exceção — se falhar, só printa no stderr
    e segue (não pode deixar o log de boot matar o boot).
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}\n"

    # Tenta o diretório padrão de logs do sistema, depois o local do projeto
    log_dirs = [
        "/var/log/tesseract-bridge",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs"),
    ]
    written = False
    for log_dir in log_dirs:
        try:
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, "boot.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line)
            written = True
            break
        except OSError:
            continue

    if not written:
        # Último recurso: stderr (capturado pelo journal no systemd)
        print(f"[boot_log] {line.strip()}", file=sys.stderr)

# Marca o início do processo — visível mesmo em falha de import total
_boot_log("=" * 60)
_boot_log(f"INICIO do processo run_bridge.py")
_boot_log(f"Python: {sys.executable}")
_boot_log(f"Versao: {sys.version.split()[0]}")
_boot_log(f"CWD:    {os.getcwd()}")
_boot_log(f"Args:   {sys.argv}")

# Nenhuma checagem de SO aqui de propósito: run_bridge.py é um processo
# Python comum, roda igual em Windows/Linux/macOS com backend=simulated
# (devices.yml). O único trecho realmente específico de hardware é
# backend=real (Raspberry Pi), e esse já falha sozinho com mensagem
# clara via o try/except em torno de RealGPIOBackend() em main() —
# não precisa de bloqueio antecipado por plataforma. Instalar como
# serviço systemd é responsabilidade só de tools/install_service.sh
# (script bash, que por si só já não roda nativamente no Windows sem
# WSL) — não é uma preocupação de run_bridge.py.

import logging
import threading
import time

_boot_log("imports stdlib OK")

# Logging colorido deve ser o primeiro import do projeto, antes de
# qualquer outro módulo que crie loggers (ou eles herdam o formatter
# padrão do Python em vez do nosso).
try:
    from logging_config import setup_logging
    _boot_log("import logging_config OK")
except ImportError as e:
    _boot_log(f"ERRO import logging_config: {e}")
    raise

setup_logging(debug="--debug" in sys.argv)

try:
    from bridge import Bridge
    _boot_log("import bridge OK")
except ImportError as e:
    _boot_log(f"ERRO import bridge: {e} — verifique se a venv esta ativada e os pacotes instalados")
    raise

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
    # Filtrar args que não são caminhos de arquivo (ex.: --debug)
    file_args = [a for a in sys.argv[1:] if not a.startswith("-")]
    config_path = file_args[0] if len(file_args) > 0 else "devices.yml"
    recipe_path = file_args[1] if len(file_args) > 1 else DEFAULT_RECIPE_PATH

    _boot_log(f"main() iniciado")
    _boot_log(f"config_path={config_path}  recipe_path={recipe_path}")
    _boot_log(f"config_path existe: {os.path.exists(config_path)}")

    ensure_config_file(config_path)

    try:
        config = BridgeConfig.load(config_path)
        _boot_log(f"devices.yml carregado OK — backend={config.backend}")
    except Exception as e:
        _boot_log(f"ERRO ao carregar devices.yml: {e}")
        raise

    if config.backend == "real":
        try:
            from gpio.real_backend import RealGPIOBackend
            backend = RealGPIOBackend()
            _boot_log("RealGPIOBackend criado OK")
        except Exception as e:
            _boot_log(f"ERRO ao criar RealGPIOBackend: {e}")
            raise
    else:
        backend = SimulatedGPIOBackend()
        _boot_log("SimulatedGPIOBackend criado OK")

    runtime = DeviceRuntime(config, backend)
    _boot_log("DeviceRuntime criado OK")

    recipe_engine = load_recipe_engine(runtime, config, recipe_path)
    _boot_log(f"recipe_engine={'ativo' if recipe_engine else 'nao carregado'}")

    bridge = Bridge(config, runtime, recipe_engine=recipe_engine)
    _boot_log("Bridge criado OK")

    if config.panel.enabled:
        app = create_panel_app(config, runtime, mqtt_status_provider(bridge, config), recipe_engine=recipe_engine)
        panel_thread = threading.Thread(
            target=lambda: app.run(host=config.panel.host, port=config.panel.port, debug=False),
            daemon=True,
        )
        panel_thread.start()
        _boot_log(f"Painel iniciado em http://{config.panel.host}:{config.panel.port}")
        print(f"Painel disponível em http://{config.panel.host}:{config.panel.port}")

    if config.mqtt.enabled:
        print(f"Conectando ao broker MQTT em {config.mqtt.host}:{config.mqtt.port}...")
    else:
        print("mqtt.enabled=false — rodando só em modo painel manual.")

    if recipe_engine is not None:
        print(f"Motor de receita ativo (status atual: {recipe_engine.state.status}).")
    else:
        print(f"Nenhuma receita em '{recipe_path}' — rodando sem motor de receita.")

    _boot_log("Processo totalmente inicializado — entrando em run_forever()")
    bridge.run_forever()


if __name__ == "__main__":
    main()
