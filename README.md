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
│   ├── base.py             # interface abstrata GPIOBackend (read/write/setup/teardown), ganhou `address` opcional
│   ├── simulated_backend.py # ✅ Fase 1 + suporte a `address` (barramento compartilhado)
│   ├── real_backend.py     # ✅ Fase 5 — gpiozero + suporte a `address` (não substitui Pi real)
│   ├── ds18b20_driver.py   # ✅ novo — driver real via filesystem 1-Wire, testado com fs fake
│   └── ds18b20_scan.py     # ✅ novo — CLI: lista sensores DS18B20 conectados e endereços
├── config.py               # ✅ Fase 2 + regra de barramento compartilhado (ds18b20 + address único)
├── device_runtime.py       # ✅ Fase 3 — ponte config <-> backend, agora repassa `address`
├── recipe_engine/          # ✅ novo (fundação) — máquina de estado de receita ainda pendente
│   ├── pid.py                # PidController (Kp/Ki/Kd, anti-windup, saída clampada)
│   └── time_proportioning.py # TimeProportioningController (duty cycle -> liga/desliga por janela)
├── failsafe_coercion.py    # ✅ Fase 4 — string do Tesseract -> tipo certo (float/bool) por subtype
├── status_handler.py       # ✅ Fase 4 — processa status agregado (LWT corrigido), matching por command_topic
├── failsafe_watchdog.py    # ✅ Fase 4 — timeout local (bridge perdeu broker, Tesseract pode estar vivo)
├── mqtt_client.py          # ✅ Fase 4 — wrapper paho-mqtt (conexão, assinatura, despacho por tópico)
├── bridge.py               # ✅ Fase 4 — orquestração (DeviceRuntime + status + watchdog + mqtt)
├── panel/                  # ✅ Fase 3 — painel/Gerenciamento (commit "melhora no html")
│   ├── app.py
│   ├── api.py
│   └── templates/index.html
├── run_panel.py            # ✅ entrada standalone — só painel, sem MQTT
├── run_bridge.py           # ✅ Fase 4 — entrada completa (MQTT + painel em paralelo)
├── tests/                   # ✅ 159 testes (ver detalhamento abaixo)
├── devices.yml.example     # ✅ atualizado para o hardware Mazza CraftBeerPi (duplo-vessel)
├── requirements.txt        # ✅
└── README.md
```

## Status do roadmap

| Fase | Item | Status |
|---|---|---|
| 1 | `gpio/base.py` + `gpio/simulated_backend.py` + testes | ✅ Concluído |
| 2 | `config.py` (carregar/validar `devices.yml`) | ✅ Concluído |
| 3 | `device_runtime.py` + `panel/` (Flask) | ✅ Concluído |
| 4 | `mqtt_client.py` + `bridge.py` + failsafe (agregado + timeout local) | ✅ Concluído |
| 5 | `gpio/real_backend.py` (gpiozero) | ✅ Concluído — wiring validado via `gpiozero.pins.mock`, **não substitui teste em Pi real** |
| 6 | Hardware Mazza CraftBeerPi: barramento DS18B20 compartilhado, driver real, scan CLI | ✅ Concluído |
| 7 | `recipe_engine/`: PID + time-proportioning (fundação) | ✅ Concluído (159/159 testes no total) |
| 8 | `recipe_engine/`: máquina de estado de receita (ramp/hold), persistência, crash-safe pause | ✅ Concluído (201/201 testes no total) |
| 9 | Painel: aba visual "Receitas" (medidor por vasilha, timeline, gráfico setpoint vs. real) | ✅ Concluído (206/206 testes no total) |

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

## Hardware alvo — Interface CraftBeerPi (MAZZA Handmade)

Esta entrega passa a mapear o hardware real do projeto: a [Interface
CLP CraftBeerPi da MAZZA Handmade](https://www.mazzahandmade.com.br/produtos/interface-clp-para-raspberrypi-automacao-cervejeira-craftbeerpi-brewpi1/)
para Raspberry Pi 4B+ (13 saídas NPN 12V 500mA digital liga/desliga, 2
bornes para sensores DS18B20 em barramento 1-Wire compartilhado em
GPIO4). `devices.yml.example` já reflete o sistema duplo-vessel
(mostura + fervura) descrito: `mash_heater`/`boil_heater` (GPIO17/27),
`pump_b1`/`pump_b2` (GPIO22/26), e os 3 sensores
`mash_tun_temp`/`boil_temp`/`chiller_out_temp` compartilhando GPIO4
distinguidos por `hardware.address` (endereço ROM do sensor). O
mapeamento de GPIO é só convenção do arquivo — pode ser alterado
livremente conforme a fiação real.

### Schema novo: sensores em barramento compartilhado (DS18B20)

`config.py` agora aceita múltiplos devices `sensor` no mesmo
`hardware.pin`, desde que todos usem `driver: ds18b20` e tenham
`hardware.address` único entre si (o ROM ID gravado de fábrica em cada
sensor) — esse é o único caso em que duplicar `pin` não é erro de
configuração. Qualquer outra combinação de pino duplicado continua
sendo rejeitada (`ConfigError`).

Para descobrir os endereços dos sensores conectados fisicamente:

```bash
python -m gpio.ds18b20_scan
```

Pré-requisito no Raspberry Pi OS (uma vez, depois reiniciar):
`dtoverlay=w1-gpio` em `/boot/firmware/config.txt` (ou `/boot/config.txt`
em versões antigas).

### Schema novo: GPIOBackend com `address`

`GPIOBackend.read/write/teardown` ganharam um parâmetro `address`
opcional (default `None`, retrocompatível com tudo que já existia) —
desambigua múltiplos devices no mesmo `pin`. `setup()` já aceitava
`**kwargs` livremente, então `address` chega por ali sem mudança de
assinatura.

### `gpio/ds18b20_driver.py` — driver real via filesystem 1-Wire

Lê `/sys/bus/w1/devices/<address>/w1_slave` (formato padrão do kernel
Linux), valida CRC, converte miligraus Celsius para float. Caminho
base injetável (`base_path`) — testado sem hardware real via
filesystem fake em `tmp_path`.

### `recipe_engine/` — fundação do motor de receitas (nova pasta)

Ainda **não inclui** a máquina de estado de receita nem a aba do
painel (próxima entrega) — só as duas peças de controle de potência,
testáveis isoladamente:

- **`pid.py`**: `PidController` clássico (Kp/Ki/Kd), anti-windup por
  clamping, saída limitada a um range configurável (default 0-100%).
  `dt` sempre explícito por chamada — nunca lê relógio internamente.
- **`time_proportioning.py`**: `TimeProportioningController` traduz a
  saída do PID (0-100%) em liga/desliga dentro de uma janela de tempo
  fixa — necessário porque as saídas da interface MAZZA são NPN
  digital simples, **não PWM analógico de hardware**. Os SSRs externos
  ("RELÉ ESTADO SÓLIDO" no diagrama da placa) seguem o sinal liga/desliga
  recebido; o controle proporcional de potência é feito por software,
  ciclando o relé dentro de cada janela.

Os devices de aquecimento (`mash_heater`, `boil_heater`) no
`devices.yml.example` por isso são `subtype: digital` (não `pwm`) — o
`DeviceRuntime`/`GPIOBackend` continuam vendo um relé liga/desliga
comum; é o `recipe_engine` (próxima entrega) que decide quando ligar e
desligar, usando PID + time-proportioning por cima.

## Motor de receita — `recipe_engine/` (Fase 8)

### ⚠️ Schema de `vessels` mudou: dict → lista com `id`/`name`/`order`

Decisão tomada em sessão de revisão: `vessels` no `recipe.yml` passou a
espelhar exatamente a convenção já usada em `devices.yml` — **lista**
de itens com `id` (referência estável, usada por `steps.vessel`) e
`name` (texto livre de exibição, ex.: `"Mostura Mash"`), em vez de
usar a chave de um dict como id implícito (o que exigia um campo
`label` separado só pra texto livre — removido). `order` (int,
opcional) controla a ordem de exibição na UI; sem ele, cai na ordem de
declaração na lista.

```yaml
vessels:
  - id: mash
    name: "Mostura"
    order: 0
    heater_device_id: mash_heater
    sensor_device_id: mash_tun_temp
    pid: { kp: 5.0, ki: 0.1, kd: 0.0 }
    window_seconds: 10
  - id: boil
    name: "Fervura"
    order: 1
    heater_device_id: boil_heater
    sensor_device_id: boil_temp
    pid: { kp: 4.0, ki: 0.05, kd: 0.0 }
```

`Recipe.vessels` (Python) também virou `List[VesselConfig]` em vez de
`Dict[str, VesselConfig]` — use `recipe.get_vessel(vessel_id)` pra
buscar por id (levanta `RecipeError` se não existir) e
`recipe.ordered_vessel_names()` pra obter a lista de ids já ordenada
por `order`.

**API HTTP não muda** (`GET /api/recipe/definition` continua
retornando `vessels` como dict por id, com a chave JSON `"label"` —
agora preenchida a partir de `VesselConfig.name`) — isso preserva o
JS do painel sem precisar editar `index.html` de novo.

Se você já tinha um `recipe.yml` no formato antigo (dict de vessels),
ele vai falhar a validação com `RecipeError` claro — converta pro
formato de lista acima.

Máquina de estado 100% autônoma — roda mesmo com `mqtt.enabled: false`,
não depende do Tesseract nem do painel pra funcionar, só do loop
principal do `bridge.py` (`run_forever`, chamado a cada
`poll_interval_seconds`, default 2s).

### Modelo de receita (`recipe.yml`, separado do `devices.yml`)

Uma receita declara `vessels` (cada uma com `heater_device_id`,
`sensor_device_id`, ganhos de PID `kp`/`ki`/`kd`, e `window_seconds`
do time-proportioning) e `steps` (cada um com `vessel`, `target_temp`,
`hold_minutes`, e `pumps` — lista de device_id de bombas ligadas
durante aquela etapa). Toda referência a device_id é validada contra
o `devices.yml` carregado no boot — falha cedo com mensagem clara se
referenciar algo que não existe. Ver `recipe.yml.example`.

### Comportamento

- **Rampa (`ramping`)**: PID calcula a saída (0-100%) a cada tick,
  `TimeProportioningController` traduz isso em liga/desliga do heater
  dentro da janela configurada. Transição pra `holding` assim que a
  leitura do sensor atinge `target_temp`.
- **Patamar (`holding`)**: decisão registrada — o tempo de patamar só
  começa a contar a partir do instante em que `target_temp` foi
  atingido, nunca desde o início da etapa. PID continua ativo durante
  o patamar (mantém a temperatura, não só "desliga e espera").
- **Bombas**: ligadas/desligadas conforme a lista `pumps` de cada
  step — comparação de conjunto a cada tick, sem esperar o próximo
  ciclo pra desligar bombas que não pertencem mais à etapa atual.
- **Avanço de etapa**: ao completar o patamar, desliga o heater da
  vasilha anterior, reseta PID e time-proportioning (evita herdar
  integral acumulado de uma etapa não relacionada), aplica as bombas
  da nova etapa imediatamente.
- **Última etapa concluída**: status `finished`, tudo desligado.

### Recuperação de crash (decisão registrada)

Se o processo cair (`kill -9`, queda de energia, qualquer encerramento
não-gracioso) no meio de `ramping`/`holding`, o **construtor** do
`RecipeEngine` detecta isso ao carregar `recipe_state.json` persistido
— não depende de nenhum signal handler nem `try/finally` de shutdown
(funciona mesmo em `SIGKILL`, que não dá chance de rodar código de
limpeza). Ao detectar, aplica `apply_failsafe` em **todos** os
atuadores `is_risk: true` do `devices.yml` inteiro (não só os da
receita — segurança ampla), marca o estado como `paused_after_crash`,
e **nunca retoma sozinho**. Validado neste teste real (não só
automatizado): processo morto com `kill -9` no meio de uma rampa,
reiniciado, heater confirmado desligado e status confirmado
`paused_after_crash` via `curl`.

Retomar exige chamada explícita a `POST /api/recipe/resume` — se a
pausa ocorreu durante `holding`, o tempo de patamar já decorrido é
preservado (não reinicia a contagem do zero).

### Aba visual "Receitas" (Fase 9)

Nova aba no painel (`panel/templates/index.html`), com identidade
visual própria — accent cobre (referência literal ao caldeirão de
cobre da brassagem), numerais em fonte monoespaçada para os
readouts de temperatura (como instrumentação industrial real), e um
**medidor circular por vasilha** como elemento de assinatura: o anel
preenche conforme a potência (`current_duty_percent`) que o PID está
aplicando naquele instante — é dado real, não decoração.

Composição da aba:
- **Cards de vasilha** (um por `vessel` da receita): medidor circular
  com temperatura atual + % de potência no centro, alvo da etapa
  atual, chips de bomba (acende quando a bomba daquela vasilha está
  ligada). Vasilha fora da etapa atual fica visualmente neutra
  ("aguardando").
- **Timeline horizontal**: um nó por step, conectados por linha —
  etapas concluídas em cobre sólido, etapa atual destacada (âmbar
  durante rampa, verde durante patamar, com label dinâmico
  "subindo…"/"em patamar…"), etapas futuras mostram alvo e tempo de
  patamar.
- **Gráfico ao vivo** (SVG desenhado em runtime, sem lib externa):
  temperatura real (linha cobre sólida) vs. setpoint (linha
  tracejada), últimos ~150 pontos de poll (~6 minutos de histórico a
  2.5s/poll) — reiniciado a cada troca de vasilha ativa.
- **Banner de crash**: aparece automaticamente quando o status é
  `paused_after_crash`, com botão "Retomar" direto.
- **Controles**: Iniciar / Cancelar, habilitados/desabilitados
  conforme o status atual.

Endpoint novo de apoio à UI: `GET /api/recipe/definition` (separado de
`/api/recipe/status`) — expõe a definição estática da receita
(vasilhas, etapas, alvos) carregada uma vez; o polling periódico
(2.5s) só bate em `/api/recipe/status` e `/api/devices` para o estado
dinâmico.

### Endpoints de receita

```
GET  /api/recipe/status      -> status de execução, vasilha/duty atual
GET  /api/recipe/definition  -> vasilhas e etapas da receita carregada
POST /api/recipe/start       -> inicia (ou reinicia do zero) a receita
POST /api/recipe/abort       -> cancela, aplica failsafe em tudo
POST /api/recipe/resume      -> retoma de paused_after_crash
```

### ⚠️ Limitação conhecida

Se um device for controlado simultaneamente por uma receita ativa E
por comando MQTT individual (`command_topic`), não há mecanismo de
prioridade/lock entre os dois — podem competir pelo mesmo atuador.
Não é um problema no uso atual (receita autônoma, MQTT tipicamente
desabilitado ou usado só para devices fora da receita), mas precisa
de uma regra de prioridade explícita se os dois forem usados ao mesmo
tempo sobre os mesmos devices.

### Rodando com receita

```bash
cp recipe.yml.example recipe.yml   # ajuste vessels/steps pra sua receita real
python run_bridge.py devices.yml recipe.yml
# ou só: python run_bridge.py   (usa devices.yml e recipe.yml por default)
```

Se `recipe.yml` não existir, o bridge roda normalmente sem motor de
receita — funcionalidade puramente opcional.

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
