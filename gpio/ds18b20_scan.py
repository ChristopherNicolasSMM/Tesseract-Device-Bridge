"""
Utilitário de linha de comando para descobrir sensores DS18B20
conectados ao barramento 1-Wire — facilita preencher `hardware.address`
no devices.yml sem precisar ler manualmente o filesystem.

Uso (no Raspberry Pi, com overlay 1-Wire habilitado):

    python -m gpio.ds18b20_scan

Pré-requisito no Pi (uma vez só, em /boot/firmware/config.txt ou
/boot/config.txt conforme a versão do Raspberry Pi OS):

    dtoverlay=w1-gpio

Depois reiniciar. Sensores no GPIO4 (pino default do overlay, e o
mesmo usado pelos bornes "SENSOR 1/2/3" da interface CraftBeerPi/MAZZA)
aparecem automaticamente em /sys/bus/w1/devices/28-*.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

from gpio.ds18b20_driver import DEFAULT_W1_BASE_PATH, Ds18b20Reader, Ds18b20ReadError

# Endereços DS18B20 sempre começam com "28-" (código de família do
# chip na convenção de nomes do kernel 1-Wire).
_DS18B20_FAMILY_PREFIX = "28-"


def scan(base_path: str = DEFAULT_W1_BASE_PATH) -> List[str]:
    """
    Lista os endereços de sensores DS18B20 atualmente visíveis no
    filesystem 1-Wire. Retorna lista vazia (não levanta erro) se o
    diretório base não existir — cenário comum quando o overlay 1-Wire
    ainda não foi habilitado, tratado como "nenhum sensor encontrado"
    em vez de falha.
    """
    base = Path(base_path)
    if not base.exists():
        return []
    return sorted(
        entry.name for entry in base.iterdir()
        if entry.is_dir() and entry.name.startswith(_DS18B20_FAMILY_PREFIX)
    )


def scan_with_readings(base_path: str = DEFAULT_W1_BASE_PATH) -> dict[str, float | str]:
    """
    Como scan(), mas já tenta ler a temperatura atual de cada sensor
    encontrado — útil pra identificar fisicamente qual sensor é qual
    (ex.: tocar no sensor da mostura com o dedo e ver qual endereço
    sobe de temperatura na lista).
    """
    results: dict[str, float | str] = {}
    for address in scan(base_path):
        try:
            reader = Ds18b20Reader(pin=4, address=address, base_path=base_path)
            results[address] = reader.value
        except Ds18b20ReadError as exc:
            results[address] = f"erro de leitura: {exc}"
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Lista sensores DS18B20 conectados.")
    parser.add_argument(
        "--base-path", default=DEFAULT_W1_BASE_PATH,
        help=f"Caminho do filesystem 1-Wire (default: {DEFAULT_W1_BASE_PATH}).",
    )
    args = parser.parse_args()

    readings = scan_with_readings(args.base_path)

    if not readings:
        print(
            f"Nenhum sensor DS18B20 encontrado em '{args.base_path}'.\n"
            f"Verifique se o overlay 1-Wire está habilitado "
            f"(dtoverlay=w1-gpio em config.txt) e se o(s) sensor(es) "
            f"estão conectados ao GPIO correto."
        )
        sys.exit(1)

    print(f"{len(readings)} sensor(es) DS18B20 encontrado(s):\n")
    for address, value in readings.items():
        if isinstance(value, float):
            print(f"  {address}  ->  {value:.3f}°C")
        else:
            print(f"  {address}  ->  {value}")
    print(
        "\nCopie o endereço correspondente para hardware.address no "
        "devices.yml. Para identificar fisicamente qual sensor é qual, "
        "toque em um sensor por vez e rode este comando de novo — o "
        "endereço cuja leitura mudar é o que você está tocando."
    )


if __name__ == "__main__":
    main()
