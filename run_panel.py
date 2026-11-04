"""Painel isolado do Device Bridge 2.0.0 para validação local.

Uso:
    python run_panel.py [--debug]

O backend do SQLite é selecionado no .env. ORM exige SIMULATION_ONLY=1
e banco normalizado. YAML não é carregado no boot.
"""

# Logging colorido antes de tudo — ver logging_config.py.
import sys
from tesseract_bridge.infrastructure.logging_config import setup_logging
setup_logging(debug="--debug" in sys.argv)

from config import BridgeConfig
from tesseract_bridge.safety.lifecycle import safety_lifecycle
from device_runtime import DeviceRuntime
from gpio.simulated_backend import SimulatedGPIOBackend
from tesseract_bridge.infrastructure.python_runtime import require_python39_for_real
from panel.app import create_panel_app

from storage.launch_config import load_runtime_config


def main() -> None:
    file_args = [arg for arg in sys.argv[1:] if not arg.startswith("-")]
    if file_args:
        raise SystemExit("Arquivo YAML não é aceito no runtime SQLite.")
    # Use exactly the same SQLite path, simulation guard and port overrides
    # as run_bridge.py; a second clone must not activate physical GPIO.
    config = load_runtime_config()

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