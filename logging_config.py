"""
Configuração de logging colorido para o Tesseract Device Bridge.

Como usar
---------
Chamar setup_logging() no início do processo (run_bridge.py ou
run_panel.py), antes de qualquer outro import que crie loggers:

    from logging_config import setup_logging
    setup_logging()

Formato de saída
----------------
    [14:32:07] INFO   bridge: Motor de receita ativo (status: idle)
    [14:32:07] WARN   gpio.real: backend selecionado: RPi.GPIO
    [14:32:07] ERROR  recipe_engine.engine: Erro ao carregar receita

O prefixo "tesseract_bridge." é removido dos nomes de módulo para
economizar espaço (fica só a parte relevante, ex.: "bridge" em vez
de "tesseract_bridge.bridge").

Cores
-----
Usam códigos ANSI padrão — funcionam em qualquer terminal Linux/Mac
e no lxterminal do Raspbian/LXDE.

    DEBUG    → cinza
    INFO     → verde
    WARNING  → amarelo
    ERROR    → vermelho
    CRITICAL → vermelho bold

Ativação de cores
-----------------
Cores são ativadas quando qualquer uma das condições é verdadeira:

    1. sys.stdout.isatty() == True
       Terminal interativo (execução manual: python run_bridge.py)

    2. FORCE_COLOR=1 no ambiente
       Processo sem TTY mas que quer cores mesmo assim (serviço
       systemd com "Environment=FORCE_COLOR=1" no .service).
       Útil porque o journald preserva os códigos ANSI e o
       logs.sh usa "journalctl --output=cat" para mostrá-los.

    3. NO_COLOR=1 no ambiente
       Desativa as cores independente do resto (útil para redirecionar
       output para arquivo ou para ambientes sem suporte a ANSI).

Nível padrão
------------
INFO. Para ver DEBUG (barulhento), passe --debug ao script:

    python run_bridge.py --debug
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

# Códigos de escape ANSI
_RESET   = "\033[0m"
_BOLD    = "\033[1m"
_GRAY    = "\033[90m"   # DEBUG
_GREEN   = "\033[92m"   # INFO
_YELLOW  = "\033[93m"   # WARNING
_RED     = "\033[91m"   # ERROR / CRITICAL
_CYAN    = "\033[96m"   # nome do módulo (destaque sutil)
_WHITE   = "\033[97m"   # timestamp e mensagem

# Mapa nível → (cor do nível, label abreviado para alinhar em 5 chars)
_LEVEL_STYLES = {
    logging.DEBUG:    (_GRAY,           "DEBUG"),
    logging.INFO:     (_GREEN,          "INFO "),
    logging.WARNING:  (_YELLOW,         "WARN "),
    logging.ERROR:    (_RED,            "ERROR"),
    logging.CRITICAL: (_RED + _BOLD,    "CRIT "),
}


def _use_colors() -> bool:
    """
    Decide se cores ANSI devem ser usadas nesta execução.
    Segue a convenção NO_COLOR / FORCE_COLOR antes de checar o TTY.
    Ver https://no-color.org/ e https://force-color.org/
    """
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


class ColoredFormatter(logging.Formatter):
    """
    Formatter que emite cada linha no formato:

        [HH:MM:SS] NIVEL  modulo: mensagem

    Com cores ANSI quando ativado (ver _use_colors()).
    Sem cores, o formato é idêntico mas sem os códigos de escape —
    assim o arquivo de log ou o journal ficam limpos.
    """

    def __init__(self, use_colors: bool = True) -> None:
        # Sem datefmt — usamos strftime manual para ter controle total
        super().__init__()
        self._use_colors = use_colors

    def _short_name(self, record: logging.LogRecord) -> str:
        """
        Remove o prefixo "tesseract_bridge." do nome do módulo.
        Ex.: "tesseract_bridge.bridge" → "bridge"
              "tesseract_bridge.gpio.real" → "gpio.real"
        """
        name = record.name
        prefix = "tesseract_bridge."
        if name.startswith(prefix):
            name = name[len(prefix):]
        return name

    def format(self, record: logging.LogRecord) -> str:
        # Formata o timestamp manualmente (sem milissegundos, mais limpo)
        import time
        timestamp = time.strftime("%H:%M:%S", time.localtime(record.created))

        level_color, level_label = _LEVEL_STYLES.get(
            record.levelno,
            (_WHITE, record.levelname[:5].upper().ljust(5))
        )
        module = self._short_name(record)
        message = record.getMessage()

        # Exceção (se houver), formatada pelo pai
        exc_text = ""
        if record.exc_info:
            exc_text = "\n" + self.formatException(record.exc_info)

        if self._use_colors:
            return (
                f"{_GRAY}[{timestamp}]{_RESET} "
                f"{level_color}{level_label}{_RESET} "
                f"{_CYAN}{module}{_RESET}: "
                f"{message}"
                f"{exc_text}"
            )
        else:
            return (
                f"[{timestamp}] {level_label} {module}: {message}{exc_text}"
            )


def setup_logging(debug: bool = False, force_colors: Optional[bool] = None) -> None:
    """
    Configura o logging raiz com o ColoredFormatter.

    Deve ser chamado uma única vez, no início do processo, antes de
    qualquer logger ser criado por outros módulos.

    Parâmetros
    ----------
    debug : bool
        True → habilita DEBUG (verbose); False (default) → só INFO+.
    force_colors : bool | None
        None  → detecta automaticamente (TTY ou FORCE_COLOR env).
        True  → força cores sempre.
        False → desativa cores sempre.
    """
    if force_colors is None:
        use_colors = _use_colors()
    else:
        use_colors = force_colors

    level = logging.DEBUG if debug else logging.INFO

    formatter = ColoredFormatter(use_colors=use_colors)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.setLevel(level)

    root = logging.getLogger()
    # Remove handlers que o Python pode ter adicionado automaticamente
    # antes desta chamada (ex.: basicConfig() implícito de alguma lib).
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Silencia loggers muito barulhentos de libs externas no nível INFO.
    # Em DEBUG, deixamos tudo passar para diagnóstico completo.
    if not debug:
        logging.getLogger("werkzeug").setLevel(logging.WARNING)
        logging.getLogger("paho").setLevel(logging.WARNING)

    # Primeira mensagem para confirmar que o logging está ativo.
    logger = logging.getLogger("tesseract_bridge.logging_config")
    logger.debug("Logging configurado: level=%s colors=%s", logging.getLevelName(level), use_colors)
