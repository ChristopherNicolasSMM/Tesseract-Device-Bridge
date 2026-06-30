"""
Driver real do sensor DS18B20, via interface 1-Wire do kernel Linux
(`/sys/bus/w1/devices/<address>/w1_slave`), exposta pelo overlay
`dtoverlay=w1-gpio` (Raspberry Pi OS) no GPIO4 — mesmo pino usado pela
interface CraftBeerPi (MAZZA Handmade) para os bornes "SENSOR 1/2/3".

Formato padrão do arquivo `w1_slave` (kernel):

    4e 01 4b 46 7f ff 0e 10 68 : crc=68 YES
    4e 01 4b 46 7f ff 0e 10 68 t=20875

Primeira linha termina em "YES" se o CRC bateu (leitura confiável).
Segunda linha tem `t=<milicelsius>` — dividir por 1000 dá °C.

Caminho base do filesystem 1-Wire é injetável (`base_path`) para
permitir teste sem hardware real — em produção é sempre o default
`/sys/bus/w1/devices`.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("tesseract_bridge.gpio.ds18b20")

DEFAULT_W1_BASE_PATH = "/sys/bus/w1/devices"


class Ds18b20ReadError(RuntimeError):
    """Falha ao ler ou parsear o arquivo w1_slave de um sensor DS18B20."""


class Ds18b20Reader:
    """
    Implementa o contrato esperado por RealGPIOBackend para devices
    `input_analog` com `driver: ds18b20` — expõe `.value` (lido sob
    demanda, sem cache, a cada acesso).

    :param pin: presente só para compatibilidade com a assinatura de
        driver esperada por register_analog_driver(pin, **kwargs) — o
        DS18B20 não é endereçado por pino diretamente (é endereçado
        pelo `address`/ROM ID via filesystem), mas o pino ainda
        importa fisicamente (precisa do overlay 1-Wire habilitado
        nele).
    :param address: ROM ID do sensor (ex.: "28-0000071234ab"),
        obrigatório — validado já em config.py antes de chegar aqui.
    :param base_path: caminho base do filesystem 1-Wire — injetável
        para teste, default é o caminho real do kernel Linux.
    """

    def __init__(self, pin: int, address: str, base_path: str = DEFAULT_W1_BASE_PATH, **kwargs: Any) -> None:
        self.pin = pin
        self.address = address
        self._device_path = Path(base_path) / address / "w1_slave"

    @property
    def value(self) -> float:
        if not self._device_path.exists():
            raise Ds18b20ReadError(
                f"Sensor DS18B20 '{self.address}' não encontrado em "
                f"'{self._device_path}'. Verifique se o overlay 1-Wire está "
                f"habilitado (dtoverlay=w1-gpio em /boot/config.txt) e se o "
                f"endereço está correto (rode gpio/ds18b20_scan.py para listar "
                f"os sensores conectados)."
            )

        raw = self._device_path.read_text(encoding="ascii")
        return self._parse(raw)

    def _parse(self, raw: str) -> float:
        lines = raw.strip().splitlines()
        if len(lines) < 2:
            raise Ds18b20ReadError(
                f"Conteúdo inesperado em '{self._device_path}': {raw!r}"
            )

        crc_line, data_line = lines[0], lines[1]
        if not crc_line.strip().endswith("YES"):
            raise Ds18b20ReadError(
                f"CRC inválido na leitura do sensor '{self.address}' "
                f"(linha: {crc_line!r}) — leitura descartada, tentar de novo."
            )

        marker = "t="
        idx = data_line.find(marker)
        if idx == -1:
            raise Ds18b20ReadError(
                f"Não encontrei 't=' na linha de dados do sensor '{self.address}': {data_line!r}"
            )

        try:
            milli_celsius = int(data_line[idx + len(marker):].strip())
        except ValueError as exc:
            raise Ds18b20ReadError(
                f"Valor de temperatura não numérico para sensor '{self.address}': {data_line!r}"
            ) from exc

        celsius = milli_celsius / 1000.0
        logger.debug("DS18B20 %s: %.3f°C", self.address, celsius)
        return celsius
