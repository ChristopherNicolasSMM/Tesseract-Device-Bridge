"""
Bridge — orquestra DeviceRuntime + MQTT (status agregado, comandos,
publicação de sensores) + watchdog de timeout local + RecipeEngine
opcional (motor de receita autônomo, ver recipe_engine/).

Dois mecanismos de fail-safe, complementares:
- StatusTopicHandler: Tesseract caiu (LWT agregado, "status: offline").
- FailsafeTimeoutWatchdog: bridge perdeu o broker, Tesseract pode estar
  vivo (timeout local por device, failsafe_timeout_seconds).

Ambos chamam, no fim das contas, DeviceRuntime.set_actuator/apply_failsafe
— um único caminho de aplicação de fail-safe, dois gatilhos diferentes.

⚠️ Limitação conhecida (não resolvida nesta entrega): se um device for
controlado ao mesmo tempo por uma receita ativa (RecipeEngine) E por
comando MQTT individual (command_topic), os dois podem competir pelo
mesmo atuador sem nenhum mecanismo de prioridade/lock entre eles. Para
o caso de uso atual (receita 100% autônoma, MQTT tipicamente
desabilitado ou usado só para os devices fora da receita) isso não é
um problema na prática, mas se os dois forem usados simultaneamente
sobre os mesmos devices, é preciso decidir uma regra de prioridade
antes — sinalizar se isso virar necessidade real.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

from config import BridgeConfig
from device_runtime import DeviceRuntime, DeviceRuntimeError
from failsafe_coercion import coerce_value
from failsafe_watchdog import FailsafeTimeoutWatchdog, devices_with_timeout
from mqtt_client import MqttClientWrapper
from recipe_engine.engine import RecipeEngine
from status_handler import StatusTopicHandler, build_command_topic_lookup

logger = logging.getLogger("tesseract_bridge.bridge")


class Bridge:
    def __init__(
        self,
        config: BridgeConfig,
        runtime: DeviceRuntime,
        recipe_engine: Optional[RecipeEngine] = None,
    ) -> None:
        self._config = config
        self._runtime = runtime
        self._recipe_engine = recipe_engine

        self._command_topic_lookup = build_command_topic_lookup(runtime, config.resolve_topic)
        self._status_handler = StatusTopicHandler(runtime, self._command_topic_lookup)
        self._watchdog = FailsafeTimeoutWatchdog(runtime, devices_with_timeout(runtime))

        self._mqtt: Optional[MqttClientWrapper] = None
        if config.mqtt.enabled:
            self._mqtt = MqttClientWrapper(
                mqtt_config=config.mqtt,
                command_topic_lookup=self._command_topic_lookup,
                on_status_message=self._status_handler.handle_message,
                on_command_message=self._handle_command_message,
                on_connect_cb=self._watchdog.on_connect,
                on_disconnect_cb=lambda: self._watchdog.on_disconnect(time.time()),
            )

    @property
    def status_handler(self) -> StatusTopicHandler:
        return self._status_handler

    @property
    def watchdog(self) -> FailsafeTimeoutWatchdog:
        return self._watchdog

    @property
    def recipe_engine(self) -> Optional[RecipeEngine]:
        return self._recipe_engine

    def _handle_command_message(self, device_id: str, payload: str) -> None:
        """
        Comando normal (não relacionado a fail-safe) chegando via
        command_topic individual de um device — ex.: o Tesseract
        mandando ligar o aquecedor a 60%.

        Aceita payload em JSON ({"value": ...}) ou valor cru — formato
        exato do lado Tesseract não fazia parte do contrato confirmado
        nesta sessão; assumido aqui, sinalizar se divergir na prática.
        """
        try:
            device = self._runtime.get_device_config(device_id)
        except KeyError:
            logger.error("Comando recebido para device desconhecido: %s", device_id)
            return

        try:
            data = json.loads(payload)
            raw_value = data.get("value", data) if isinstance(data, dict) else data
        except json.JSONDecodeError:
            raw_value = payload

        value = coerce_value(raw_value, device.subtype)
        try:
            self._runtime.set_actuator(device_id, value)
            logger.info("Comando aplicado: device=%s valor=%s", device_id, value)
        except DeviceRuntimeError as exc:
            logger.error("Falha ao aplicar comando em '%s': %s", device_id, exc)

    def publish_sensor_states(self) -> None:
        if self._mqtt is None:
            return
        for device in self._runtime.list_device_configs():
            if device.role == "sensor" and device.state_topic:
                state = self._runtime.get_state(device.id)
                topic = self._config.resolve_topic(device.state_topic)
                self._mqtt.publish(topic, json.dumps({"value": state.value}), qos=0, retain=False)

    def check_watchdog(self, now: float) -> list[str]:
        return self._watchdog.check(now)

    def tick_recipe(self, now: float) -> None:
        if self._recipe_engine is not None:
            self._recipe_engine.tick(now)

    def start(self) -> None:
        if self._mqtt:
            self._mqtt.connect()

    def stop(self) -> None:
        if self._mqtt:
            self._mqtt.disconnect()

    def run_forever(self, poll_interval_seconds: float = 2.0) -> None:
        self.start()
        try:
            while True:
                now = time.time()
                self.publish_sensor_states()
                self.check_watchdog(now)
                self.tick_recipe(now)
                time.sleep(poll_interval_seconds)
        except KeyboardInterrupt:
            logger.info("Encerrando bridge (KeyboardInterrupt).")
        finally:
            self.stop()
