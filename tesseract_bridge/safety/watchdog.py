"""
FailsafeTimeoutWatchdog — cobre o cenário "bridge perdeu conexão com o
broker, mas o Tesseract pode estar vivo" (o StatusTopicHandler cobre o
cenário oposto: "Tesseract caiu", via LWT agregado).

Os dois mecanismos são complementares, nunca duplicados — cada um cobre
metade do espaço de falhas possível.

`now` é sempre recebido por parâmetro (nunca lido internamente via
time.time()) para o watchdog ser testável sem sleep real.
"""

from __future__ import annotations

from typing import List, Optional, Set

from config import DeviceConfig
from device_runtime import DeviceRuntime


class FailsafeTimeoutWatchdog:
    def __init__(self, runtime: DeviceRuntime, devices_with_timeout: List[DeviceConfig]) -> None:
        self._runtime = runtime
        self._devices = devices_with_timeout
        self._disconnected_since: Optional[float] = None
        self._applied_ids: Set[str] = set()

    def on_disconnect(self, now: float) -> None:
        self._disconnected_since = now
        self._applied_ids = set()

    def on_connect(self) -> None:
        self._disconnected_since = None
        self._applied_ids = set()

    def check(self, now: float) -> List[str]:
        """
        Verifica se algum device passou do timeout desde a última
        desconexão e aplica failsafe localmente. Retorna a lista de
        device_ids em que o failsafe foi aplicado nesta chamada (vazia
        na maioria das chamadas — só não-vazia no instante em que o
        timeout é cruzado).
        """
        if self._disconnected_since is None:
            return []

        elapsed = now - self._disconnected_since
        applied_now: List[str] = []

        for device in self._devices:
            if device.id in self._applied_ids:
                continue
            if elapsed >= device.failsafe_timeout_seconds:
                self._runtime.apply_failsafe(device.id)
                self._applied_ids.add(device.id)
                applied_now.append(device.id)

        return applied_now


def devices_with_timeout(runtime: DeviceRuntime) -> List[DeviceConfig]:
    return [
        device
        for device in runtime.list_device_configs()
        if device.is_risk and device.failsafe_timeout_seconds is not None
    ]
