# tesseract-device-bridge

Componente independente (não faz parte do repositório Tesseract, não segue
as skills 00–04 do Tesseract) que roda no Raspberry Pi (ou qualquer máquina
com GPIO/sensores) fazendo a ponte entre hardware físico e o broker MQTT.

Especificação completa de origem:
`docs/skills/05-proposta-addon-device-manager-e-mqtt.md` (lado Tesseract) +
spec deste componente (lado bridge).

## Decisões registradas desta fase

- **Repositório**: novo e separado do Tesseract. Compatibilidade com o
  `addon_device_manager` é só por convenção de nomes de chave no
  `devices.yml` — sem link automático ou submódulo.
- **`failsafe_timeout_seconds`**: promovido de "fora de escopo" para
  entregável da v1. Para cada atuador com `is_risk: true` e esse campo
  definido, o bridge aplica `failsafe_value` localmente se ficar sem
  conexão MQTT por mais tempo que o limite — complementa (não substitui)
  o LWT registrado pelo lado Tesseract.
- **Segurança do painel web**: decisão consciente de não ter autenticação
  na v1. O painel aciona atuadores reais diretamente, sem RBAC. Assume-se
  rede local confiável. **Se for exposto fora da rede local, é
  responsabilidade de quem fizer o deploy colocar atrás de VPN ou
  reverse-proxy com autenticação** — isso não é tratado pelo código deste
  repositório.

## Estrutura

```
tesseract-device-bridge/
├── gpio/
│   ├── base.py             # interface abstrata GPIOBackend (read/write/setup/teardown)
│   ├── simulated_backend.py # ✅ implementado e testado (Fase 1)
│   └── real_backend.py     # ✅ Fase 5 — gpiozero, validado via mock (não substitui Pi real)
├── config.py               # ✅ implementado e testado (Fase 2)
├── device_runtime.py       # ✅ implementado e testado (Fase 3) — ponte config <-> backend
├── failsafe_coercion.py    # ✅ Fase 4 — string do Tesseract -> tipo certo (float/bool) por subtype
├── status_handler.py       # ✅ Fase 4 — processa status agregado (LWT corrigido), matching por command_topic
├── failsafe_watchdog.py    # ✅ Fase 4 — timeout local (bridge perdeu broker, Tesseract pode estar vivo)
├── mqtt_client.py          # ✅ Fase 4 — wrapper paho-mqtt (conexão, assinatura, despacho por tópico)
├── bridge.py               # ✅ Fase 4 — orquestração (DeviceRuntime + status + watchdog + mqtt)
├── panel/                  # ✅ implementado e testado (Fase 3)
│   ├── app.py
│   ├── api.py
│   └── templates/index.html
├── run_panel.py            # ✅ entrada standalone — só painel, sem MQTT
├── run_bridge.py           # ✅ Fase 4 — entrada completa (MQTT + painel em paralelo)
├── tests/                   # ✅ 102 testes (ver detalhamento abaixo)
├── devices.yml.example     # ✅
├── requirements.txt        # ✅
└── README.md
```

## Status do roadmap

| Fase | Item | Status |
|---|---|---|
| 1 | `gpio/base.py` + `gpio/simulated_backend.py` + testes | ✅ Concluído |
| 2 | `config.py` (carregar/validar `devices.yml`) | ✅ Concluído |
| 3 | `device_runtime.py` + `panel/` (Flask) | ✅ Concluído |
| 4 | `mqtt_client.py` + `bridge.py` + failsafe (agregado + timeout local) | ✅ Concluído (102/102 testes no total) |
| 5 | `gpio/real_backend.py` (gpiozero) | ✅ Concluído — wiring validado via `gpiozero.pins.mock`, **não substitui teste em Pi real** |

## ⚠️ Sobre a validação da Fase 5

Os testes de `gpio/real_backend.py` usam `gpiozero.pins.mock` (MockFactory +
MockPWMPin) — confirmam que o mode certo instancia a classe gpiozero certa
e que valores são escritos/lidos na escala esperada (PWM em 0–100, não
0.0–1.0 do gpiozero). **Isso não é prova de que o hardware físico funciona.**
Primeiro teste real em Pi: rodar com `backend: real` no `devices.yml` e
confirmar visualmente que o pino correspondente liga/desliga / varia PWM.

`input_analog` (ex.: `driver: ds18b20` do `devices.yml.example`) não tem
implementação real ainda — só o mecanismo de registro
(`register_analog_driver()`). Implementar o driver real do ds18b20 (via
`w1thermsensor` ou leitura direta do filesystem 1-Wire) é trabalho futuro,
só quando houver o sensor físico disponível para validar.

## ⚠️ Acoplamento implícito com o repositório Tesseract (Core)

A correção de protocolo MQTT (1 LWT por conexão, não por atuador) já
está incorporada aqui. Pontos que dependem de convenção compartilhada
com o lado Tesseract, sem nenhuma validação automática entre os dois
repositórios:

- **Tópico de status**: `system/tesseract/status` (relativo, resolvido
  com `topic_prefix`) — constante hardcoded em `mqtt_client.py`
  (`STATUS_TOPIC_RELATIVE`). Se o lado Tesseract mudar essa string, a
  mensagem simplesmente nunca chega aqui — sem erro visível.
- **Matching de atuador é por `command_topic` completo**, nunca por
  `external_id` (que é um UUID interno do `DeviceActor`, sem vínculo
  com o `id` do `devices.yml`).
- **`failsafe_value` chega como string** do lado Tesseract — coercido
  aqui conforme o `subtype` do device local (`pwm`/`analog`/`temperature`
  → float, `digital`/desconhecido → bool).
- **Mensagem de status é retained (qos=1)**, mas estática até o próximo
  reconnect do lado Tesseract — tratada aqui como snapshot, nunca como
  garantia de estar atualizada.
- **Ao voltar para `status: "online"`, nenhuma ação automática** —
  atuador em failsafe só sai desse estado ao receber um comando normal
  (decisão registrada nesta sessão).
- **Formato do payload de comando normal (`command_topic` individual)
  não fez parte do contrato confirmado** — `bridge.py` assume JSON
  `{"value": ...}` ou valor cru como fallback; se o formato real do
  Tesseract divergir, ajustar `Bridge._handle_command_message`.

## Rodando o bridge completo (MQTT + painel)

```bash
pip install -r requirements.txt
cp devices.yml.example devices.yml   # ajuste mqtt.host para o broker real
python run_bridge.py
```

## Rodando o painel isoladamente (sem MQTT)

```bash
pip install -r requirements.txt
cp devices.yml.example devices.yml   # ou aponte para outro arquivo
python run_panel.py
# abrir http://localhost:8088
```

## Bugs corrigidos

- **`run_panel.py` falhava com `ConfigError` se `devices.yml` não existisse** —
  causa raiz: `main()` chamava `BridgeConfig.load(config_path)` direto, sem
  nenhum bootstrap; em um clone novo do repositório só existe
  `devices.yml.example`, nunca `devices.yml`. Corrigido com
  `ensure_config_file()`: se o caminho não existir, copia
  `devices.yml.example` para esse caminho antes de carregar. Se o exemplo
  também não existir, levanta `ConfigError` explícito em vez de deixar o
  erro de cópia subir cru. Nunca sobrescreve um `devices.yml` já existente.

## Rodando os testes

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```
