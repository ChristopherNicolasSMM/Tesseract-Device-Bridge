"""
Roda o painel manual isoladamente, sem MQTT — útil para testar o
hardware (real ou simulado) sem broker nem Tesseract de pé.

Uso:
    python run_panel.py [caminho/para/devices.yml]
    python run_panel.py --debug   # ativa logs de nível DEBUG

Se omitido, usa `data/public/devices.yml`. Se o arquivo não existir, é
criado automaticamente a partir de `data/public/devices.yml.example`
(cópia, nunca symlink) — assim o primeiro `python run_panel.py` depois
em instalações novas, banco SQLite criado com configuração simulada segura.
"""

# Logging colorido antes de tudo — ver logging_config.py.
import sys
from logging_config import setup_logging
setup_logging(debug="--debug" in sys.argv)

from config import BridgeConfig
from safety_lifecycle import safety_lifecycle
from device_runtime import DeviceRuntime
from gpio.simulated_backend import SimulatedGPIOBackend
from python_runtime import require_python39_for_real
from panel.app import create_panel_app

from storage import sqlite_store as store


def main() -> None:
    file_args = [arg for arg in sys.argv[1:] if not arg.startswith("-")]
    if file_args:
        raise SystemExit("Arquivo YAML não é aceito no runtime SQLite.")
    store.initialize(seed=True)
    config = BridgeConfig.from_dict(store.load_config())
    config.validate()

    if config.backend == "real":
        require_python39_for_real()
        from gpio.real_backend import RealGPIOBackend  # implementado na Fase 5
        backend = RealGPIOBackend()
    else:
        backend = SimulatedGPIOBackend()

    runtime = DeviceRuntime(config, backend)
    with safety_lifecycle(runtime):
        app = create_panel_app(config, runtime)

        print(f"Painel disponível em http://{config.panel.host}:{config.panel.port}")
        app.run(host=config.panel.host, port=config.panel.port, debug=False)

if __name__ == "__main__":
    main()
#Modo real testar |   python -m gpio.ds18b20_scan