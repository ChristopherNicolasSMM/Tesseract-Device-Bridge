"""
Roda o painel manual isoladamente, sem MQTT — útil para testar o
hardware (real ou simulado) sem broker nem Tesseract de pé.

Uso:
    python run_panel.py [caminho/para/devices.yml]

Se omitido, usa `devices.yml` na raiz do projeto.
"""

import sys

from config import BridgeConfig
from device_runtime import DeviceRuntime
from gpio.simulated_backend import SimulatedGPIOBackend
from panel.app import create_panel_app


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "devices.yml"
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
