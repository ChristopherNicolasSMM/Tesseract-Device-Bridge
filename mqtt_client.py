"""
Wrapper sobre paho-mqtt. Toda a lógica de decisão (o que fazer com cada
mensagem) já está em status_handler.py / failsafe_watchdog.py / bridge.py
— este módulo só conecta, assina e despacha por tópico.

Constante importante: STATUS_TOPIC_RELATIVE precisa ficar idêntica à
convenção fixa do lado Tesseract (`system/tesseract/status`, ver
mqtt_client_service.status_topic()). Isso é acoplamento implícito entre
os dois repositórios — se um lado mudar essa string, o outro quebra
silenciosamente (a mensagem simplesmente nunca chega).
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, Optional

import paho.mqtt.client as mqtt

from config import MqttConfig

logger = logging.getLogger("tesseract_bridge.mqtt_client")

STATUS_TOPIC_RELATIVE = "system/tesseract/status"


class MqttClientWrapper:
    """
    :param on_status_message: callable(payload_str) -> None — chamado
        para mensagens no tópico de status agregado.
    :param on_command_message: callable(device_id, payload_str) -> None
        — chamado para mensagens em command_topic de um device local.
    :param on_connect_cb: callable() -> None — chamado quando a conexão
        é (re)estabelecida.
    :param on_disconnect_cb: callable() -> None — chamado quando a
        conexão cai.
    """

    def __init__(
        self,
        mqtt_config: MqttConfig,
        command_topic_lookup: Dict[str, str],
        on_status_message: Callable[[str], None],
        on_command_message: Callable[[str, str], None],
        on_connect_cb: Optional[Callable[[], None]] = None,
        on_disconnect_cb: Optional[Callable[[], None]] = None,
    ) -> None:
        self._config = mqtt_config
        self._command_topic_lookup = command_topic_lookup
        self._on_status_message = on_status_message
        self._on_command_message = on_command_message
        self._on_connect_cb = on_connect_cb
        self._on_disconnect_cb = on_disconnect_cb

        self._status_topic_full = f"{mqtt_config.topic_prefix}/{STATUS_TOPIC_RELATIVE}"

        self._client = mqtt.Client(client_id=mqtt_config.client_id)
        if mqtt_config.username:
            self._client.username_pw_set(mqtt_config.username, mqtt_config.password)
        self._client.on_connect = self._handle_connect
        self._client.on_disconnect = self._handle_disconnect
        self._client.on_message = self._handle_message

    def connect(self) -> None:
        self._client.connect(self._config.host, self._config.port)
        self._client.loop_start()

    def disconnect(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    def publish(self, topic: str, payload: str, qos: int = 0, retain: bool = False) -> None:
        self._client.publish(topic, payload, qos=qos, retain=retain)

    def _handle_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        logger.info("Conectado ao broker MQTT (%s:%s).", self._config.host, self._config.port)
        client.subscribe(self._status_topic_full, qos=1)
        for command_topic in self._command_topic_lookup:
            client.subscribe(command_topic, qos=1)
        if self._on_connect_cb:
            self._on_connect_cb()

    def _handle_disconnect(self, client, userdata, *args) -> None:
        logger.warning("Desconectado do broker MQTT.")
        if self._on_disconnect_cb:
            self._on_disconnect_cb()

    def _handle_message(self, client, userdata, msg) -> None:
        topic = msg.topic
        try:
            payload = msg.payload.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning("Payload não-UTF8 recebido em '%s', ignorando.", topic)
            return

        if topic == self._status_topic_full:
            self._on_status_message(payload)
            return

        device_id = self._command_topic_lookup.get(topic)
        if device_id is not None:
            self._on_command_message(device_id, payload)
            return

        logger.debug("Mensagem em tópico não tratado: %s", topic)
