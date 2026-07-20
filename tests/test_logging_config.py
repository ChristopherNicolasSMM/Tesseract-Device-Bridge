"""
Testes do ColoredFormatter e setup_logging().

Não dependem de terminal real (TTY) — testam o formatter diretamente,
passando use_colors explicitamente, sem depender de isatty() ou
variáveis de ambiente.
"""

import logging
import os

import pytest

from logging_config import ColoredFormatter, setup_logging, _use_colors


# ---- ColoredFormatter sem cores (modo serviço/arquivo) --------------------

def test_plain_format_contains_level_and_message():
    formatter = ColoredFormatter(use_colors=False)
    record = logging.LogRecord(
        name="tesseract_bridge.bridge",
        level=logging.INFO,
        pathname="", lineno=0, msg="Motor de receita ativo",
        args=(), exc_info=None,
    )
    output = formatter.format(record)
    assert "INFO" in output
    assert "bridge" in output
    assert "Motor de receita ativo" in output


def test_plain_format_strips_prefix_from_module_name():
    """
    "tesseract_bridge.gpio.real" deve virar "gpio.real" na saída —
    economiza espaço e remove ruído repetitivo.
    """
    formatter = ColoredFormatter(use_colors=False)
    record = logging.LogRecord(
        name="tesseract_bridge.gpio.real",
        level=logging.DEBUG,
        pathname="", lineno=0, msg="backend selecionado: RPi.GPIO",
        args=(), exc_info=None,
    )
    output = formatter.format(record)
    assert "gpio.real" in output
    assert "tesseract_bridge" not in output


def test_plain_format_contains_timestamp():
    formatter = ColoredFormatter(use_colors=False)
    record = logging.LogRecord(
        name="test", level=logging.INFO,
        pathname="", lineno=0, msg="teste",
        args=(), exc_info=None,
    )
    output = formatter.format(record)
    # Timestamp no formato [HH:MM:SS]
    assert "[" in output and "]" in output
    # O conteúdo entre colchetes deve ter 2 dois-pontos (HH:MM:SS)
    bracket_content = output[output.index("[") + 1 : output.index("]")]
    assert bracket_content.count(":") == 2


def test_plain_warn_label_is_WARN_not_WARNING():
    """WARNING é longo; abreviamos para WARN pra alinhar com ERROR (5 chars)."""
    formatter = ColoredFormatter(use_colors=False)
    record = logging.LogRecord(
        name="test", level=logging.WARNING,
        pathname="", lineno=0, msg="aviso",
        args=(), exc_info=None,
    )
    output = formatter.format(record)
    assert "WARN" in output
    # Não deve aparecer como "WARNING" completo (seria mais longo que ERROR)
    assert "WARNING" not in output


# ---- ColoredFormatter com cores -------------------------------------------

def test_colored_format_contains_ansi_codes():
    formatter = ColoredFormatter(use_colors=True)
    record = logging.LogRecord(
        name="test", level=logging.INFO,
        pathname="", lineno=0, msg="mensagem com cor",
        args=(), exc_info=None,
    )
    output = formatter.format(record)
    # Código de escape ANSI deve estar presente
    assert "\033[" in output


def test_colored_format_ends_with_reset_code():
    """A linha deve terminar com reset pra não vazar cor para a próxima."""
    formatter = ColoredFormatter(use_colors=True)
    record = logging.LogRecord(
        name="test", level=logging.ERROR,
        pathname="", lineno=0, msg="erro",
        args=(), exc_info=None,
    )
    output = formatter.format(record)
    # \033[0m é o reset — deve aparecer na linha
    assert "\033[0m" in output


def test_colored_format_still_contains_message():
    """Cores não devem engolir a mensagem."""
    formatter = ColoredFormatter(use_colors=True)
    record = logging.LogRecord(
        name="test", level=logging.INFO,
        pathname="", lineno=0, msg="mensagem importante",
        args=(), exc_info=None,
    )
    output = formatter.format(record)
    assert "mensagem importante" in output


# ---- _use_colors() — lógica de detecção ------------------------------------

def test_no_color_env_disables_colors(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    assert _use_colors() is False


def test_force_color_env_enables_colors(monkeypatch):
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert _use_colors() is True


def test_no_color_takes_precedence_over_force_color(monkeypatch):
    """NO_COLOR tem prioridade — convencão de https://no-color.org/"""
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert _use_colors() is False


# ---- setup_logging() -------------------------------------------------------

def test_setup_logging_sets_info_level_by_default():
    setup_logging(debug=False, force_colors=False)
    root = logging.getLogger()
    assert root.level == logging.INFO


def test_setup_logging_sets_debug_level_when_debug_true():
    setup_logging(debug=True, force_colors=False)
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    # Restaurar para não afetar outros testes
    setup_logging(debug=False, force_colors=False)


def test_setup_logging_does_not_duplicate_handlers():
    """Chamar setup_logging() múltiplas vezes não deve acumular handlers."""
    setup_logging(force_colors=False)
    setup_logging(force_colors=False)
    setup_logging(force_colors=False)
    root = logging.getLogger()
    assert len(root.handlers) == 1


def test_setup_logging_installs_colored_formatter():
    setup_logging(force_colors=True)
    root = logging.getLogger()
    assert len(root.handlers) >= 1
    formatter = root.handlers[0].formatter
    assert isinstance(formatter, ColoredFormatter)
    assert formatter._use_colors is True
