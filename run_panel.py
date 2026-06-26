"""
Roda o painel manual isoladamente, sem MQTT — útil para testar o
hardware (real ou simulado) sem broker nem Tesseract de pé.

Uso:
    python run_panel.py [caminho/para/devices.yml]

Se omitido, usa `devices.yml` na raiz do projeto. Se o arquivo não
existir, é criado automaticamente a partir de `devices.yml.example`
(cópia, nunca symlink) — assim o primeiro `python run_panel.py` depois
de um clone novo já funciona, sem passo manual de "copie o exemplo".
"""

import shutil
import sys
from pathlib import Path

from config import BridgeConfig, ConfigError
from device_runtime import DeviceRuntime
from gpio.simulated_backend import SimulatedGPIOBackend
from panel.app import create_panel_app

EXAMPLE_CONFIG_PATH = "devices.yml.example"


def ensure_config_file(path: str) -> None:
    """
    Garante que `path` existe antes de tentar carregar. Se não existir,
    copia `devices.yml.example` para esse caminho. Se o exemplo também
    não existir, levanta ConfigError com mensagem explícita em vez de
    deixar o erro de cópia subir cru.
    """
    config_path = Path(path)
    if config_path.exists():
        return

    example_path = Path(EXAMPLE_CONFIG_PATH)
    if not example_path.exists():
        raise ConfigError(
            f"'{config_path}' não existe e '{example_path}' (modelo padrão) "
            f"também não foi encontrado — não há como criar automaticamente."
        )

    config_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(example_path, config_path)
    print(f"'{config_path}' não encontrado — criado a partir de '{example_path}'.")


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "devices.yml"
    ensure_config_file(config_path)
    config = BridgeConfig.load(config_path)

    if config.backend == "real":
        from gpio.real_backend import RealGPIOBackend  # implementado na Fase 5
        backend = RealGPIOBackend()
    else:
        backend = SimulatedGPIOBackend()

    runtime = DeviceRuntime(config, backend)
    app = create_panel_app(config, runtime)

    print(f"Painel disponível em http://{config.panel.host}:{config.panel.port}")
    app.run(host=config.panel.host, port=config.panel.port, debug=False)


if __name__ == "__main__":
    main()
