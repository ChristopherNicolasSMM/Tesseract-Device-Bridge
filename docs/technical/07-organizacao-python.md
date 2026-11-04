# 07 — Organização dos módulos Python | 2.0.0

> Branch: `feature/sqlite-full-migration`. Refatoração sem mudança
> deliberada na lógica de PID, intertravamentos ou GPIO.

## Diretriz de arquitetura

Adotamos uma transição do layout plano para um pacote interno
`tesseract_bridge/`, mantendo os entrypoints `run_bridge.py` e
`run_panel.py` e as interfaces públicas usadas pelo Flask.

A PEP 8 recomenda nomes de pacotes/módulos em minúsculas e imports
absolutos claros; o Python Packaging User Guide documenta os layouts
*flat* e *src*. Neste estágio, o layout *flat* é mantido para preservar
a execução direta do serviço systemd e os comandos já utilizados no
Windows sem impor uma instalação `pip install -e .`.

## Estrutura

```text
Tesseract-Device-Bridge/
├── .env.example
├── .gitignore
├── .python-version
├── pyproject.toml                # pytest / Ruff, sem build wheel
├── run_bridge.py                # boot do processo completo
├── run_panel.py                 # boot do painel independente
├── bridge.py                    # orquestração: preservado nesta etapa
├── config.py                    # BridgeConfig: preservado nesta etapa
├── device_runtime.py            # GPIO real: preservado nesta etapa
├── control_settings.py          # validação térmica
├── temperature_calibration.py   # calibração física
├── tesseract_bridge/
│   ├── version.py
│   ├── infrastructure/
│   │   ├── env.py               # .env e overrides por processo
│   │   ├── paths.py             # local raiz e dados
│   │   ├── logging_config.py
│   │   └── python_runtime.py
│   ├── safety/
│   │   ├── failsafe_coercion.py
│   │   ├── watchdog.py
│   │   └── lifecycle.py
│   ├── control/
│   │   ├── source_control.py
│   │   ├── time_proportioning.py
│   │   └── remote_device_control.py
│   └── integrations/
│       ├── mqtt_client.py
│       └── status_handler.py
├── gpio/
├── recipe_engine/
├── panel/
├── storage/                      # SQLite; evolução via ORM
├── tools/
├── tests/
└── docs/
```

## Contrato de compatibilidade

Os comandos permanecem:

```powershell
python run_bridge.py
python run_panel.py
python -m storage.cli status
```

Imports internos agora devem usar `tesseract_bridge.<subpacote>`.
Scripts externos que importavam diretamente `source_control`,
`infra_env`, `version` etc. precisam atualizar os caminhos.
Não existem importações globais de GPIO nos `__init__.py`.

**Não movemos** `device_runtime.py`, `config.py`, `bridge.py`
nem o motor de receitas nesta entrega: sua migração exige análise de
interfaces externas e testes elétricos separados.

## Comandos de validação

```powershell
python -m compileall -q .
python -m pytest -q tests/test_package_layout.py tests/test_infra_env.py tests/test_app_version.py tests/test_logging_config.py tests/test_python_runtime.py tests/test_failsafe_coercion.py tests/test_failsafe_watchdog.py tests/test_time_proportioning.py tests/test_source_control.py tests/test_status_handler.py tests/test_bridge.py
python -m storage.cli status
```

No Windows mantenha `TESSERACT_BRIDGE_SIMULATION_ONLY=1` no .env.
A mudança estrutural não autoriza teste de GPIO real.

Referências:
- [PEP 8](https://peps.python.org/pep-0008/)
- [Python Packaging User Guide: src layout e flat layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)
