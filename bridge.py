"""
Bridge — orquestra DeviceRuntime + MQTT (status agregado, comandos,
publicação de sensores) + watchdog de timeout local + RecipeEngine
opcional (motor de receita autônomo, ver recipe_engine/).

Dois mecanismos de fail-safe, complementares:
- StatusTopicHandler: Tesseract caiu (LWT agregado, "status: offline").
- FailsafeTimeoutWatchdog: bridge perdeu o broker, Tesseract pode estar
  vivo (timeout local por device, failsafe_timeout_seconds).

Ambos chamam, no fim das contas, DeviceRuntime.apply_failsafe/
apply_failsafe_external — um único caminho de aplicação de fail-safe,
dois gatilhos diferentes.

Prioridade entre receita ativa (RecipeEngine) e comando MQTT/painel
individual sobre o mesmo atuador (resolvida — ver device_runtime.py):
para atuadores com hardware.window_seconds, DeviceRuntime é o dono
único do GPIO — failsafe > override manual > duty da receita > repouso.
Isso substitui a limitação de "sem lock de prioridade" registrada
anteriormente aqui e no README.
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

        Devices com controle de potência (hardware.window_seconds) são
        roteados como override manual de duty (0-100%), nunca como
        liga/desliga puro — mesmo que o subtype declarado seja
        "digital" (isso descreve o tipo físico do GPIO, não como o
        valor de comando deve ser interpretado). raw_value None (ex.:
        payload JSON {"value": null}) limpa o override, devolvendo o
        controle pra receita ativa (se houver) ou repouso.
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

        if device.has_duty_control:
            try:
                duty_percent = None if raw_value is None else coerce_value(raw_value, "pwm")
                self._runtime.set_manual_duty(device_id, duty_percent)
                logger.info("Duty manual aplicado via MQTT: device=%s duty=%s", device_id, duty_percent)
            except DeviceRuntimeError as exc:
                logger.error("Falha ao aplicar duty em '%s': %s", device_id, exc)
            return

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

    def tick_duty(self, now: float) -> None:
        """
        Avança o controle de potência de todo atuador com
        hardware.window_seconds — precisa rodar mesmo sem receita
        carregada (cobre override manual isolado). Chamado depois de
        tick_recipe() no loop principal, pra já refletir o duty que a
        receita acabou de calcular neste mesmo ciclo.
        """
        self._runtime.tick_duty(now)

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
                self.tick_duty(now)
                time.sleep(poll_interval_seconds)
        except KeyboardInterrupt:
            logger.info("Encerrando bridge (KeyboardInterrupt).")
        finally:
            self.stop()
