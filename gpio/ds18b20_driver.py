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

Leitura em thread de fundo (não bloqueia requisição HTTP)
-----------------------------------------------------------
Ler `w1_slave` no Linux dispara uma conversão nova no sensor a cada
chamada — o kernel bloqueia a leitura até o resultado sair, tipicamente
~750-950ms (comportamento do driver w1-therm, não é bug daqui). Sem
cache, cada `/api/devices` do painel, ao ler N sensores DS18B20 em
sequência, travava a requisição inteira por N × ~800ms.

Este driver resolve isso com uma thread dedicada por sensor: a
PRIMEIRA leitura é síncrona (só acontece uma vez, dentro de __init__,
que roda durante o boot do bridge — nunca durante uma requisição), e
paga o custo real de ~750-950ms ali. Depois disso, uma thread de fundo
(`daemon=True`) fica lendo em loop a cada `poll_interval_seconds`
(default 1.0s), guardando sempre o último valor bom. `.value` nunca
bloqueia — devolve o que está em cache, instantâneo.

Se as leituras em background começarem a falhar (CRC ruim — comum em
1-Wire por ruído elétrico —, ou sensor desconectado), a thread loga o
erro e mantém o último valor bom, sem derrubar nada. Só depois de
`stale_after_seconds` (default 10s) sem NENHUMA leitura bem-sucedida é
que `.value` passa a levantar `Ds18b20ReadError` de verdade — evita
tanto "trava tudo a cada glitch" quanto "mostra um valor de 20 minutos
atrás pra sempre, calado".
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("tesseract_bridge.gpio.ds18b20")

DEFAULT_W1_BASE_PATH = "/sys/bus/w1/devices"
DEFAULT_POLL_INTERVAL_SECONDS = 1.0
DEFAULT_STALE_AFTER_SECONDS = 10.0


class Ds18b20ReadError(RuntimeError):
    """Falha ao ler ou parsear o arquivo w1_slave de um sensor DS18B20."""


class Ds18b20Reader:
    """
    Implementa o contrato esperado por RealGPIOBackend para devices
    `input_analog` com `driver: ds18b20` — expõe `.value`, sempre
    instantâneo (lê de uma thread de fundo, nunca bloqueia a chamada —
    ver docstring do módulo).

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
    :param poll_interval_seconds: intervalo entre leituras da thread de
        fundo. Opcional em devices.yml (hardware.poll_interval_seconds);
        default 1.0s — não faz sentido menor que o tempo de conversão
        real do sensor (~750-950ms).
    :param stale_after_seconds: tempo máximo sem NENHUMA leitura bem-
        sucedida antes de `.value` passar a levantar erro em vez de
        devolver um valor cada vez mais antigo calado. Opcional em
        devices.yml (hardware.stale_after_seconds); default 10.0s.
    """

    def __init__(
        self,
        pin: int,
        address: str,
        base_path: str = DEFAULT_W1_BASE_PATH,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
        **kwargs: Any,
    ) -> None:
        self.pin = pin
        self.address = address
        self._device_path = Path(base_path) / address / "w1_slave"
        self._poll_interval = poll_interval_seconds
        self._stale_after = stale_after_seconds
        self._lock = threading.Lock()

        # Primeira leitura é síncrona e bloqueante de propósito — só
        # acontece uma vez, aqui, durante o boot (RealGPIOBackend.setup()
        # chama isto uma vez por device, nunca numa requisição HTTP).
        # Isso também faz o construtor levantar Ds18b20ReadError na hora
        # se o sensor não responder — falha cedo e visível no boot, em
        # vez de só aparecer depois, mascarada, no primeiro poll.
        initial_value = self._read_once()
        self._cached_value: float = initial_value
        self._last_success_at: float = time.monotonic()
        self._last_error: Optional[Exception] = None

        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._poll_loop,
            name=f"ds18b20-poll-{address}",
            daemon=True,
        )
        self._thread.start()

    def _poll_loop(self) -> None:
        # wait() primeiro: a leitura inicial já aconteceu de forma
        # síncrona em __init__, então o primeiro ciclo daqui é a
        # SEGUNDA leitura, poll_interval_seconds depois da primeira.
        # Retorna True se _stop_event foi sinalizado (para o loop),
        # False se só deu timeout (caso normal, continua lendo).
        while not self._stop_event.wait(self._poll_interval):
            try:
                value = self._read_once()
                with self._lock:
                    self._cached_value = value
                    self._last_success_at = time.monotonic()
                    self._last_error = None
            except Ds18b20ReadError as exc:
                logger.warning(
                    "Leitura em background do DS18B20 %s falhou (mantendo último valor bom em cache): %s",
                    self.address, exc,
                )
                with self._lock:
                    self._last_error = exc

    def _read_once(self) -> float:
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

    @property
    def value(self) -> float:
        with self._lock:
            cached = self._cached_value
            last_success_at = self._last_success_at
            last_error = self._last_error

        age = time.monotonic() - last_success_at
        if age > self._stale_after:
            raise Ds18b20ReadError(
                f"Sensor DS18B20 '{self.address}' sem leitura válida há "
                f"{age:.1f}s (limite: {self._stale_after}s) — último erro "
                f"da thread de fundo: {last_error}"
            )
        return cached

    def close(self) -> None:
        """
        Encerra a thread de leitura em background — chamado por
        RealGPIOBackend.teardown() (mesmo mecanismo genérico usado para
        os devices gpiozero, via hasattr(device, "close")).
        """
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=self._poll_interval + 1.0)

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
