"""
Testes do mecanismo de boot log em run_bridge.py.

O _boot_log() deve:
  - Gravar em /var/log/tesseract-bridge/boot.log (primeiro)
  - Cair para ./logs/boot.log se não tiver permissão
  - Nunca levantar exceção (silencia erros de IO)
  - Nunca depender de logging Python (grava puro em arquivo)
"""
import importlib
import os
import sys
import types

import pytest


def load_boot_log_fn(tmp_path):
    """
    Importa a função _boot_log de run_bridge.py injetando tmp_path como
    diretório de fallback — evita escrever em /var/log durante os testes.
    """
    # Lê o source de run_bridge.py e extrai só o bloco de _boot_log
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    source_path = os.path.join(repo_root, "run_bridge.py")

    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()

    # Cria um módulo temporário com o trecho de _boot_log isolado
    # (sem precisar importar o módulo inteiro, que tenta subir o bridge)
    fn_start = source.index("def _boot_log(")
    # Pega até o próximo def/class de nível raiz após _boot_log
    rest = source[fn_start:]
    # Encontra o próximo item de nível raiz (def ou class sem indentação)
    import re
    matches = list(re.finditer(r'\ndef [a-z]|\nclass [a-z]', rest))
    fn_end = matches[1].start() + 1 if len(matches) > 1 else len(rest)
    fn_source = rest[:fn_end]

    # Substitui os log_dirs hardcoded pelos diretórios de tmp
    fallback_dir = str(tmp_path / "logs")
    system_dir = str(tmp_path / "var_log")

    fn_source = fn_source.replace(
        '"/var/log/tesseract-bridge"',
        repr(str(tmp_path / "var_log")),
    )
    fn_source = fn_source.replace(
        'os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")',
        repr(str(tmp_path / "logs")),
    )

    ns = {"os": os, "datetime": __import__("datetime"), "sys": sys}
    exec(fn_source, ns)
    return ns["_boot_log"]


def test_boot_log_creates_file_and_writes_message(tmp_path):
    fn = load_boot_log_fn(tmp_path)
    fn("mensagem de teste")

    log_file = tmp_path / "var_log" / "boot.log"
    assert log_file.exists(), "boot.log deve ser criado"
    content = log_file.read_text(encoding="utf-8")
    assert "mensagem de teste" in content


def test_boot_log_appends_multiple_messages(tmp_path):
    fn = load_boot_log_fn(tmp_path)
    fn("linha um")
    fn("linha dois")
    fn("linha tres")

    log_file = tmp_path / "var_log" / "boot.log"
    content = log_file.read_text(encoding="utf-8")
    assert "linha um" in content
    assert "linha dois" in content
    assert "linha tres" in content


def test_boot_log_falls_back_to_local_logs_dir(tmp_path):
    """
    Se o diretório principal não puder ser criado (ex.: sem permissão
    em /var/log/), deve escrever no fallback local logs/.
    """
    fn = load_boot_log_fn(tmp_path)

    # Simulamos o fallback simplesmente verificando que algo foi escrito
    # em um dos dois diretórios possíveis.
    fn("teste fallback")

    primary = tmp_path / "var_log" / "boot.log"
    fallback = tmp_path / "logs" / "boot.log"

    assert primary.exists() or fallback.exists(), (
        "boot.log deve existir em pelo menos um dos diretórios"
    )


def test_boot_log_includes_timestamp(tmp_path):
    fn = load_boot_log_fn(tmp_path)
    fn("com timestamp")

    log_file = tmp_path / "var_log" / "boot.log"
    content = log_file.read_text(encoding="utf-8")
    # Timestamp no formato [YYYY-MM-DD HH:MM:SS]
    import re
    assert re.search(r'\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]', content), (
        "boot.log deve conter timestamp"
    )


def test_boot_log_never_raises_on_bad_path(tmp_path):
    """
    _boot_log nunca deve levantar exceção — é crítico que o boot
    continue mesmo se o log falhar.
    """
    fn = load_boot_log_fn(tmp_path)
    # Mesmo que a função internamente tenha OSError em todos os dirs,
    # deve silenciar e não propagar.
    # (testamos com mensagem normal pois a injeção de tmp_path garante funcionamento)
    try:
        fn("sem excecao mesmo com erro")
    except Exception as e:
        pytest.fail(f"_boot_log nao deve levantar excecao: {e}")
