# 01 — Visão Geral Técnica

> **Navegação:** [README](../../README.md) | [C4 Diagrams](02-diagrama-c4.md) | [Fluxos](03-fluxos.md) | [Modelo de Dados](04-modelo-de-dados.md) | [Casos de Uso](05-casos-de-uso.md) | [Manutenção](06-manutencao-e-expansao.md)

## Propósito

O `tesseract-device-bridge` é o componente de hardware do ecossistema
Tesseract: roda num Raspberry Pi (ou qualquer Linux com GPIO), lê sensores,
aciona atuadores, executa automação de processo via PID + time-proportioning
e se conecta ao Tesseract Core via MQTT quando disponível.

Nasce com um caso de uso concreto — controle de mostura de cervejaria —
mas o núcleo é genérico: tudo que é específico de domínio vive em
`devices.yml` e `recipe.yml`, não no código.

## Estrutura de arquivos

```
tesseract-device-bridge/
│
├── run_bridge.py           # Ponto de entrada completo (MQTT + painel + receita)
├── run_panel.py            # Ponto de entrada só-painel (sem MQTT, sem receita)
├── logging_config.py       # Logs coloridos com ColoredFormatter
│
├── bridge.py               # Orquestração: loop principal, tick_recipe, watchdog
├── config.py               # Carrega e valida devices.yml → BridgeConfig
├── device_runtime.py       # Ponte config ↔ GPIO backend (lê/escreve devices)
├── failsafe_coercion.py    # Coerce failsafe_value string → tipo pelo subtype
├── failsafe_watchdog.py    # Timeout local por device (failsafe_timeout_seconds)
├── mqtt_client.py          # Wrapper paho-mqtt: connect, subscribe, publish
├── status_handler.py       # Processa LWT agregado do Tesseract → aplica failsafe
│
├── gpio/
│   ├── base.py             # GPIOBackend (interface abstrata)
│   ├── simulated_backend.py # Backend em memória (testes / bancada sem hardware)
│   ├── real_backend.py     # Backend gpiozero com seleção automática de pin factory
│   ├── ds18b20_driver.py   # Driver DS18B20 (1-Wire via /sys/bus/w1/devices/)
│   └── ds18b20_scan.py     # CLI: lista sensores DS18B20 conectados ao barramento
│
├── recipe_engine/
│   ├── models.py           # Recipe, Vessel, Step, HopAlarm (schema + validação)
│   ├── state.py            # RecipeState + AlarmEvent (persistência JSON)
│   ├── engine.py           # RecipeEngine (PID + TPC + alarmes + crash recovery)
│   ├── pid.py              # PidController (Kp/Ki/Kd, anti-windup por clamping)
│   └── time_proportioning.py # TimeProportioningController (duty cycle → liga/desliga)
│
├── panel/
│   ├── app.py              # Flask factory — cria a app com recipe_engine opcional
│   ├── api.py              # Blueprint /api/* — endpoints REST
│   └── templates/
│       └── index.html      # SPA single-file (CSS + JS embutidos, 3 abas)
│
├── tools/
│   ├── gpio_test.py        # Ferramenta interativa de diagnóstico de GPIO (sem devices.yml)
│   ├── install_service.sh  # Instala serviço systemd + autostart LXDE
│   ├── uninstall_service.sh # Remove serviço e autostart
│   └── logs.sh             # Mostra logs ao vivo (journalctl --output=cat)
│
├── devices.yml.example     # Exemplo MAZZA CraftBeerPi (3 sensores DS18B20 + 4 atuadores)
├── recipe.yml.example      # Exemplo: Pilsen Clássica (mostura + fervura + hop_alarms)
│
└── tests/                  # 283+ testes (pytest)
```

## Dependências externas

| Pacote | Versão mínima | Uso |
|---|---|---|
| `flask` | 2.x | Painel web (API REST + SPA) |
| `paho-mqtt` | 1.6+ | Cliente MQTT (LWT, subscribe, publish) |
| `gpiozero` | 1.6+ | Abstração de GPIO (pin factories: lgpio, RPi.GPIO, pigpio) |
| `PyYAML` | 6.x | Carga e validação de `devices.yml` e `recipe.yml` |
| `pytest` | 7.x | Suite de testes |

**Backend GPIO (uma das opções abaixo, instalada separadamente):**

| Pacote | OS alvo | Como instalar |
|---|---|---|
| `RPi.GPIO` | Raspbian / Pi OS Bullseye / Buster | `pip install RPi.GPIO` |
| `lgpio` | Pi OS Bookworm / Pi 5 | `pip install lgpio` |
| `pigpio` | Qualquer (requer daemon) | `pip install pigpio && sudo pigpiod` |

O bridge tenta os backends nessa ordem: lgpio → RPi.GPIO → pigpio. O backend
escolhido aparece no log ao iniciar:

```
[14:32:07] INFO  gpio.real: backend selecionado: RPi.GPIO (rpigpio)
```

## API HTTP (painel web em `http://<pi>:8088`)

### Devices

| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/api/status` | Status MQTT do broker |
| GET | `/api/devices` | Lista todos os devices com valores ao vivo |
| GET | `/api/devices/<id>` | Estado de um device específico |
| POST | `/api/devices/<id>/command` | Aciona atuador com `{"value": ...}` |
| POST | `/api/devices/<id>/simulate` | Injeta valor em sensor (só backend simulado) |

### Receita

| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/api/recipe/status` | Status de execução, vasilha ativa, duty, alarmes, tempos |
| GET | `/api/recipe/definition` | Definição estática (vasilhas + etapas) |
| POST | `/api/recipe/start` | Inicia (ou reinicia do zero) |
| POST | `/api/recipe/abort` | Cancela — aplica failsafe em tudo |
| POST | `/api/recipe/pause` | Pausa manual — aplica failsafe, aguarda resume |
| POST | `/api/recipe/resume` | Retoma de `paused_manual` ou `paused_after_crash` |
| POST | `/api/recipe/skip_next` | Força avanço para a próxima etapa |
| POST | `/api/recipe/skip_previous` | Volta para a etapa anterior (reinicia do zero) |
| POST | `/api/recipe/reset_step` | Reinicia a etapa atual sem mudar de posição |
| POST | `/api/recipe/alarms/<id>/ack` | Confirma (dispensa) alarme pendente |

## MQTT (quando `mqtt.enabled: true`)

| Tópico | Direção | Conteúdo |
|---|---|---|
| `<prefix>/sensors/<id>/state` | Bridge → broker | Valor atual do sensor (float/bool) |
| `<prefix>/actuators/<id>/set` | broker → Bridge | Comando de atuador (`{"value": ...}`) |
| `<prefix>/system/tesseract/status` | broker → Bridge | LWT agregado do Tesseract (failsafe) |

## Logs coloridos

O sistema usa `logging_config.py` com um `ColoredFormatter` que emite no formato:

```
[HH:MM:SS] NIVEL  modulo: mensagem
```

| Nível | Cor |
|---|---|
| DEBUG | Cinza |
| INFO | Verde |
| WARNING | Amarelo |
| ERROR | Vermelho |
| CRITICAL | Vermelho bold |

Cores ativadas quando: TTY interativo (execução manual) **ou** `FORCE_COLOR=1`
(serviço systemd — o arquivo `.service` define essa variável automaticamente).
Desativado com `NO_COLOR=1`. Para nível DEBUG: passe `--debug` ao script.

## Documentos relacionados

| | |
|---|---|
| [02 — Diagramas C4](02-diagrama-c4.md) | Contexto, Container, Componente |
| [03 — Fluxos de execução](03-fluxos.md) | Receita, crash, MQTT, GPIO, serviço |
| [04 — Modelo de dados](04-modelo-de-dados.md) | ER de devices.yml, recipe.yml, recipe_state.json |
| [05 — Casos de uso](05-casos-de-uso.md) | UCs com flowcharts e sequence diagrams |
| [06 — Manutenção e expansão](06-manutencao-e-expansao.md) | Como estender, adaptar, deploy |
