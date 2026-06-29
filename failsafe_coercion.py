"""
Coerção de valores vindos do Tesseract via MQTT.

O `failsafe_value` no payload de status agregado sempre chega como
string (coluna String(50) no banco do lado Tesseract — ver confirmação
do contrato real). Quem decide o tipo final é o bridge, com base no
`subtype` do device local correspondente.
"""

from __future__ import annotations

_TRUE_STRINGS = {"true", "1", "on", "yes"}


def coerce_value(raw: object, subtype: str | None) -> object:
    """
    Converte um valor recebido (string, na prática) para o tipo correto
    de acordo com o subtype do device local:

    - "pwm" / "analog" / "temperature" -> float
    - "digital" / None (default)       -> bool

    Valores que já chegam no tipo certo (ex.: testes passando float/bool
    diretamente) são aceitos sem conversão redundante.
    """
    if subtype in ("pwm", "analog", "temperature"):
        if isinstance(raw, (int, float)):
            return float(raw)
        return float(str(raw).strip().replace(",", "."))

    # digital (ou subtype desconhecido) -> bool
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in _TRUE_STRINGS
