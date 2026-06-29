"""
Roda o bridge completo: MQTT (status agregado + comandos + publicação
de sensores) e, opcionalmente, o painel manual em paralelo (mesmo
DeviceRuntime compartilhado, então uma ação no painel reflete
imediatamente no que seria publicado via MQTT).

Uso:
    python run_bridge.py [caminho/para/devices.yml]
"""

import sys
import threading

from bridge import Bridge
from config import BridgeConfig
from device_runtime import DeviceRuntime
from gpio.simulated_backend import SimulatedGPIOBackend
from panel.app import create_panel_app
from run_panel import ensure_config_file


def mqtt_status_provider(bridge: Bridge, config: BridgeConfig):
    def _provider() -> str:
        if not config.mqtt.enabled:
            return "disabled"
        return bridge.status_handler.last_status or "unknown"
    return _provider


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
    bridge = Bridge(config, runtime)

    if config.panel.enabled:
        app = create_panel_app(config, runtime, mqtt_status_provider(bridge, config))
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

    bridge.run_forever()


if __name__ == "__main__":
    main()
