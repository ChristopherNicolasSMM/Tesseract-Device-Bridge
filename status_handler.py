"""
StatusTopicHandler — processa o payload agregado de status publicado
pelo Tesseract no tópico `system/tesseract/status` (LWT corrigido:
um único LWT por conexão, payload JSON listando os atuadores de risco).

Matching feito por `command_topic` totalmente resolvido (não por
external_id) — contrato confirmado: external_id é um UUID do
DeviceActor sem nenhum vínculo com o `id` legível do devices.yml do
bridge; o único campo presente nos dois lados é command_topic.

Mensagem retained (qos=1, retain=true) -> tratada como snapshot do
momento da última conexão do Tesseract, nunca como garantia de estar
atualizada em tempo real (confirmado: lista é estática até reconnect
do lado Tesseract).
 
Comportamento ao voltar para "online": nenhum (decisão registrada) —
atuador permanece no failsafe_value até receber um comando normal.
"""

from __future__ import annotations

import json
import logging
from typing import Dict, Optional

from device_runtime import DeviceRuntime, DeviceRuntimeError
from failsafe_coercion import coerce_value

logger = logging.getLogger("tesseract_bridge.status_handler")


class StatusTopicHandler:
    def __init__(self, runtime: DeviceRuntime, command_topic_lookup: Dict[str, str]) -> None:
        """
        :param command_topic_lookup: {command_topic_completo: device_id_local}
            pré-computado a partir do devices.yml (config.resolve_topic()
            aplicado a cada device.command_topic local).
        """
        self._runtime = runtime
        self._lookup = command_topic_lookup
        self.last_status: Optional[str] = None

    def handle_message(self, payload: str) -> None:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("Payload de status não é JSON válido, ignorando: %r", payload)
            return

        status = data.get("status")
        self.last_status = status

        if status == "offline":
            self._apply_failsafe_from_payload(data)
        elif status == "online":
            logger.info("Tesseract reportou status=online — nenhuma ação automática (decisão registrada).")
        else:
            logger.warning("Payload de status com campo 'status' inesperado: %r", status)

    def _apply_failsafe_from_payload(self, data: dict) -> None:
        for entry in data.get("failsafe_actuators", []):
            command_topic = entry.get("command_topic")
            device_id = self._lookup.get(command_topic)
            if device_id is None:
                # Atuador conhecido pelo Tesseract mas não cadastrado
                # neste devices.yml (ou ainda em transição) — ignora
                # silenciosamente, não é erro.
                continue

            try:
                device = self._runtime.get_device_config(device_id)
                value = coerce_value(entry.get("failsafe_value"), device.subtype)
                self._runtime.apply_failsafe_external(device_id, value)
                logger.warning(
                    "Failsafe aplicado via status agregado: device=%s valor=%s (Tesseract offline)",
                    device_id, value,
                )
            except (DeviceRuntimeError, KeyError) as exc:
                logger.error("Falha ao aplicar failsafe em '%s': %s", device_id, exc)


def build_command_topic_lookup(runtime: DeviceRuntime, resolve_topic) -> Dict[str, str]:
    """
    Constrói {command_topic_completo: device_id} para todos os devices
    locais que são actuator e têm command_topic — usado para montar o
    StatusTopicHandler.

    :param resolve_topic: callable (ex.: BridgeConfig.resolve_topic) que
        aplica o topic_prefix a um tópico relativo.
    """
    lookup: Dict[str, str] = {}
    for device in runtime.list_device_configs():
        if device.role == "actuator" and device.command_topic:
            lookup[resolve_topic(device.command_topic)] = device.id
    return lookup
