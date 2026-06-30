# tesseract-device-bridge

> Ponte entre hardware físico (GPIO de um Raspberry Pi) e automação de
> processo — com ou sem rede.

## O que é este projeto

Este repositório é a **metade física** do [Tesseract](https://github.com/ChristopherNicolasSMM/Tesseract):
roda dentro do Raspberry Pi (ou qualquer máquina Linux com GPIO),
falando diretamente com sensores e atuadores, e se conecta ao
Tesseract via MQTT quando disponível. Ele nasceu com um objetivo
concreto — **controlar uma mostura de cervejaria caseira** (PID de
temperatura por vasilha, bombas, timers de lupulagem) — mas a
arquitetura **não tem nada de cervejeiro embutido no núcleo**. Tudo
que é específico de brassagem vive em dois lugares isolados:

- **`devices.yml`** — descreve *o que está fisicamente ligado em quais
  pinos* (sensores, relés, bombas). Trocar o domínio é trocar este
  arquivo.
- **`recipe.yml`** — descreve *o processo a automatizar* (vasilhas,
  etapas, alvos, alarmes). Também é só configuração.

O núcleo (`gpio/`, `device_runtime.py`, `bridge.py`,
`recipe_engine/`) não sabe o que é "mostura" ou "lúpulo" — ele sabe
ler sensores, acionar atuadores, rodar PID + time-proportioning por
"vasilha" (qualquer coisa controlada por um sensor + um aquecedor/atuador
+ um alvo), e disparar alarmes por etapa. **Isso significa que dá pra
reaproveitar o projeto inteiro pra controlar qualquer sistema que siga
o mesmo padrão "sensor → controlador → atuador, em etapas com um
alvo"** — irrigação por zona (umidade do solo → válvula), estufa
(temperatura/umidade → ventilação/aquecimento), tanque de processo
industrial, etc. — sem tocar no núcleo, só escrevendo um `devices.yml`
e um `recipe.yml` novos (e, se o domínio precisar de um tipo de sensor
diferente do DS18B20, implementando um driver novo em `gpio/`, seguindo
o padrão já estabelecido por `ds18b20_driver.py`).

Essa generalidade é o que torna o projeto uma base razoável pra
integrar com plataformas de automação agrícola maiores (ex.: Conecta
Agro e similares) — o bridge já resolve a parte difícil e repetitiva
(leitura confiável de sensores 1-Wire, controle PID com proteção
contra falha, recuperação de queda de energia, alarmes programáveis,
painel web pronto) e deixa só a modelagem do processo (`recipe.yml`)
e o mapeamento de hardware (`devices.yml`) como trabalho específico de
cada novo domínio.

## Por que existe separado do Tesseract

Não é um Addon do Tesseract nem segue as skills 00–04 dele — é um
processo Python independente, com seu próprio repositório, pensado
pra rodar isolado no hardware (inclusive **sem internet/MQTT
nenhum**, em modo só-painel-local). A compatibilidade com o
`addon_device_manager` do Tesseract é por convenção de protocolo
(tópicos MQTT, formato de payload), nunca por dependência de código.

---

## Visão geral rápida

```
devices.yml   -> o que está ligado em qual pino (hardware real)
recipe.yml    -> o processo a automatizar (opcional — sem ele, o bridge
                 ainda funciona como painel manual + ponte MQTT pura)

run_panel.py  -> só o painel web, sem MQTT, sem motor de receita
                 (bom pra testar hardware isolado na bancada)
run_bridge.py -> processo completo: painel + MQTT (se habilitado) +
                 motor de receita (se recipe.yml existir)
```

| Camada | Arquivo(s) | Especificidade de domínio? |
|---|---|---|
| GPIO abstrato | `gpio/base.py`, `simulated_backend.py`, `real_backend.py` | Nenhuma |
| Drivers de sensor | `gpio/ds18b20_driver.py` (+ scan CLI) | Nenhuma (1-Wire genérico) |
| Config de hardware | `config.py`, `devices.yml` | Só o que você descrever |
| Runtime de device | `device_runtime.py` | Nenhuma |
| Ponte MQTT | `mqtt_client.py`, `status_handler.py`, `failsafe_watchdog.py`, `bridge.py` | Nenhuma |
| Painel web | `panel/` | Genérico (lista sensores/atuadores quaisquer) + aba "Receitas" |
| Motor de processo | `recipe_engine/` | Nenhuma — "vasilha" é só um nome, pode ser zona de irrigação, estufa, tanque |
| Modelagem do processo | `recipe.yml` | **Aqui mora toda a especificidade de domínio** |

---

## Instalação e primeiro uso

```bash
git clone <este-repositorio>
cd tesseract-device-bridge
pip install -r requirements.txt

# Só painel, pra testar hardware (cria devices.yml a partir do exemplo automaticamente):
python run_panel.py
# abrir http://localhost:8088

# Processo completo (painel + MQTT se habilitado + receita se existir):
cp devices.yml.example devices.yml      # ajuste pinos/sensores reais
cp recipe.yml.example recipe.yml        # opcional — defina o processo
python run_bridge.py
```

`devices.yml`/`recipe.yml` nunca são sobrescritos se já existirem —
`run_panel.py`/`run_bridge.py` só criam a partir do `.example`
correspondente na primeira vez que rodam num diretório novo.

### Diferença entre `run_panel.py` e `run_bridge.py`

| | `run_panel.py` | `run_bridge.py` |
|---|---|---|
| Painel web | ✅ | ✅ |
| MQTT (Tesseract) | ❌ nunca | ✅ se `mqtt.enabled: true` |
| Motor de receita | ❌ nunca | ✅ se `recipe.yml` existir |
| Failsafe por timeout de conexão | ❌ | ✅ |
| Uso típico | bancada, debug de hardware isolado | operação real |

---

## Hardware suportado

A configuração de exemplo (`devices.yml.example`) mapeia a [Interface
CLP CraftBeerPi da MAZZA Handmade](https://www.mazzahandmade.com.br/produtos/interface-clp-para-raspberrypi-automacao-cervejeira-craftbeerpi-brewpi1/)
para Raspberry Pi 4B+ — 13 saídas NPN 12V 500mA digital liga/desliga
(não é PWM de hardware: potência variável é feita por software via
time-proportioning, ver seção do motor de receita) e sensores DS18B20
em barramento 1-Wire compartilhado (GPIO4 por padrão, vários sensores
no mesmo pino, cada um identificado pelo `hardware.address` — endereço
ROM gravado de fábrica). Mas **nada no código depende dessa placa
específica** — qualquer Raspberry Pi com GPIO comum e sensores 1-Wire
funciona, só ajustando os pinos no `devices.yml`.

Pra descobrir os endereços dos sensores DS18B20 conectados:

```bash
python -m gpio.ds18b20_scan
```

Pré-requisito no Raspberry Pi OS (uma vez, depois reiniciar):
`dtoverlay=w1-gpio` em `/boot/firmware/config.txt` (ou
`/boot/config.txt` em versões antigas).

### Schema de dispositivo compartilhando pino (sensores 1-Wire)

`config.py` aceita múltiplos devices `sensor` no mesmo `hardware.pin`
desde que todos usem `driver: ds18b20` e tenham `hardware.address`
único entre si — único caso em que duplicar `pin` não é erro de
configuração.

---

## Motor de receita (`recipe_engine/`)

Máquina de estado **100% autônoma** — funciona com `mqtt.enabled: false`
e sem o Tesseract de pé, dirigida só pelo loop principal de
`bridge.py`. Cada `vessel` (vasilha — ou zona, tanque, o que o seu
domínio precisar) tem seu próprio `PidController` +
`TimeProportioningController`; cada `step` da receita declara qual
vasilha controla, o alvo (`target_temp`), quanto tempo segurar
(`hold_minutes`), quais atuadores extras ligar (`pumps`), e
opcionalmente alarmes de etapa (`hop_alarms`).

### Schema do `recipe.yml`

```yaml
name: "Pilsen Clássica"

vessels:
  - id: mash               # referência estável, usada em steps.vessel
    name: "Mostura"         # texto livre de exibição
    order: 0                 # ordem de exibição na UI (opcional)
    heater_device_id: mash_heater
    sensor_device_id: mash_tun_temp
    pid: { kp: 5.0, ki: 0.1, kd: 0.0 }
    window_seconds: 10       # janela de time-proportioning

  - id: boil
    name: "Fervura"
    order: 1
    heater_device_id: boil_heater
    sensor_device_id: boil_temp
    pid: { kp: 4.0, ki: 0.05, kd: 0.0 }

steps:
  - vessel: mash
    label: "Mostura - Sacarificação"
    target_temp: 67
    hold_minutes: 60
    pumps: [pump_b1]

  - vessel: boil
    label: "Fervura"
    target_temp: 100
    hold_minutes: 60
    pumps: [pump_b2]
    hop_alarms:                          # opcional — só faz sentido pra brassagem,
      - minutes_remaining: 60             # mas é só dado, não código especial
        label: "Lúpulo Amargor - 30g Magnum"
      - minutes_remaining: 0
        label: "Whirlpool - fim da fervura"
```

`vessels` é uma **lista** (não dict), espelhando a convenção já usada
em `devices.yml`: `id` é a referência estável usada por `steps.vessel`,
`name` é texto livre de exibição. Toda referência a `device_id`
(`heater_device_id`, `sensor_device_id`, `pumps`) é validada contra o
`devices.yml` carregado no boot — falha cedo, com mensagem clara, se
referenciar algo que não existe.

### Comportamento de execução

- **Rampa (`ramping`)**: PID calcula a saída (0-100%) a cada tick;
  `TimeProportioningController` traduz isso em liga/desliga do
  atuador dentro da janela configurada (necessário porque a maioria
  dos relés de automação industrial/agrícola é liga/desliga simples,
  não PWM analógico). Transição pra `holding` assim que o sensor
  atinge `target_temp`.
- **Patamar (`holding`)**: o tempo só começa a contar a partir do
  instante em que o alvo foi atingido — nunca desde o início da
  etapa. O PID continua ativo durante o patamar, mantendo o alvo.
- **Atuadores extras (`pumps`)**: ligados/desligados conforme a lista
  de cada etapa, reavaliado a cada tick.
- **Avanço de etapa**: desliga o atuador principal da vasilha
  anterior, reseta PID/time-proportioning (evita herdar acúmulo de
  uma etapa não relacionada), aplica os atuadores extras da nova
  etapa imediatamente.

### Controles manuais (API + painel)

```
GET  /api/recipe/status        -> status de execução, vasilha/duty, tempo total/decorrido
GET  /api/recipe/definition    -> vasilhas e etapas da receita carregada
POST /api/recipe/start         -> inicia (ou reinicia do zero) a receita
POST /api/recipe/abort         -> cancela, aplica failsafe em tudo
POST /api/recipe/pause         -> pausa deliberada — aplica failsafe, espera resume
POST /api/recipe/resume        -> retoma de paused_after_crash OU paused_manual
POST /api/recipe/skip_next     -> força avanço pra próxima etapa (ignora tempo/temperatura)
POST /api/recipe/skip_previous -> volta pra etapa anterior (reinicia ela do zero)
POST /api/recipe/reset_step    -> reinicia a etapa atual sem mudar de etapa
POST /api/recipe/alarms/<id>/ack -> confirma (dispensa) um alarme pendente
```

No painel (aba "Receitas"): barra de transporte com 4 botões
(anterior `⏮` / reiniciar etapa `↺` / play-pause `⏯` / próxima `⏭`),
cronômetro grande mostrando tempo restante do patamar (ou decorrido
da rampa), medidor circular por vasilha (anel preenche conforme a
potência real aplicada pelo PID), timeline horizontal de etapas, e
gráfico ao vivo de temperatura real vs. setpoint.

### Recuperação de crash

Se o processo cair (`kill -9`, queda de energia, qualquer
encerramento não-gracioso) no meio de `ramping`/`holding`, o
**construtor** do `RecipeEngine` detecta isso ao carregar
`recipe_state.json` persistido — não depende de signal handler nem
`try/finally` (funciona mesmo em `SIGKILL`). Aplica failsafe em
**todos** os atuadores `is_risk: true` do `devices.yml` (segurança
ampla, não só os da receita), marca `paused_after_crash`, e **nunca
retoma sozinho** — exige `POST /api/recipe/resume` explícito, que
preserva o tempo de patamar já decorrido se a pausa ocorreu durante
`holding`. Validado com teste real (não só automatizado): processo
morto com `kill -9` no meio de uma rampa, reiniciado, atuador
confirmado desligado e status confirmado via `curl`.

### Timers de alarme

Dois mecanismos, ambos expostos via `pending_alarms` em
`/api/recipe/status`:

- **Eventos automáticos de vasilha** (`vessel_start`/`vessel_end`):
  sem nenhuma configuração — disparam toda vez que a vasilha muda
  entre uma etapa e a seguinte (ou no início/fim absoluto da
  execução). Generaliza "Início Mostura"/"Final Fervura" (ou
  "Início Irrigação Zona 2", etc.) pra qualquer vasilha que a receita
  declarar. Etapas consecutivas da mesma vasilha não disparam nada
  entre si — só nas transições reais.
- **Alarmes por etapa** (`hop_addition` no código, mas é um nome
  genérico — serve pra qualquer evento programado dentro de uma
  etapa): lista opcional `hop_alarms` por `step`, cada item com
  `minutes_remaining` (contagem regressiva pro **fim** do patamar) +
  `label` livre.

Ações manuais (`skip_previous`/`reset_current_step`) não disparam
alarmes automáticos; `skip_next` dispara, porque segue o mesmo caminho
interno de quando uma etapa termina naturalmente.

**UI**: banner em destaque (borda pulsante) aparece automaticamente
via polling quando há alarme pendente. Som sintetizado via Web Audio
API (3 opções embutidas — Beep, Sirene, Campainha — geradas em
runtime, sem nenhum arquivo de áudio binário no repositório) ou som
próprio (upload, salvo em `localStorage` do navegador). Regra de
parada: toca pelo número de repetições configurado **ou** para no
clique em "OK", o que vier primeiro.

---

## Painel web

Single-page app em `panel/templates/index.html`, três abas:

- **Painel** — lista de sensores/atuadores ao vivo, com controle
  manual direto (liga/desliga, ajustar valor simulado) — útil pra
  testar hardware sem depender de receita nem MQTT.
- **Gerenciamento** — tabela de inventário dos devices configurados.
- **Receitas** — interface completa do motor de processo (ver seção
  acima).

⚠️ **Sem autenticação** — decisão consciente de v1, não omissão. O
painel aciona atuadores reais diretamente, sem RBAC. Assume-se rede
local confiável. Se for exposto fora da rede local, é responsabilidade
de quem fizer o deploy colocar atrás de VPN ou reverse-proxy com
autenticação.

---

## Acoplamento com o Tesseract (Core)

Pontos que dependem de convenção compartilhada com o lado Tesseract,
sem nenhuma validação automática entre os dois repositórios:

- **Tópico de status agregado**: `system/tesseract/status` (relativo,
  resolvido com `topic_prefix`) — constante hardcoded em
  `mqtt_client.py` (`STATUS_TOPIC_RELATIVE`). Se o lado Tesseract
  mudar essa string, a mensagem nunca chega aqui, sem erro visível.
- **Matching de atuador é por `command_topic` completo**, nunca por
  `external_id` (UUID interno do Tesseract, sem vínculo com o `id` do
  `devices.yml` local).
- **`failsafe_value` chega como string** do lado Tesseract — coercido
  aqui conforme o `subtype` do device local.
- **Mensagem de status MQTT é retained (qos=1)**, mas estática até o
  próximo reconnect do lado Tesseract — tratada aqui como snapshot,
  nunca como garantia de estar atualizada em tempo real.
- **Ao voltar para `status: "online"`, nenhuma ação automática** — um
  atuador em failsafe só sai desse estado recebendo um comando normal.
- **Formato do payload de comando individual** (`command_topic`) não
  foi formalmente contratado — `bridge.py` assume JSON `{"value": ...}`
  ou valor cru como fallback.

## Limitações conhecidas

- Sem lock de prioridade entre receita ativa e comando MQTT individual
  sobre o mesmo device — podem competir pelo mesmo atuador se usados
  simultaneamente sobre os mesmos devices. Não é problema no uso atual
  (receita autônoma, MQTT tipicamente desabilitado ou usado só pra
  devices fora da receita).
- `input_analog` sem driver registrado levanta `NotImplementedError`
  explícito — só `ds18b20` está implementado; outros tipos de sensor
  analógico (útil pra outros domínios — umidade do solo, pH, etc.)
  exigem implementar um driver novo seguindo o padrão de
  `gpio/ds18b20_driver.py` + `register_analog_driver()`.
- Testes de `gpio/real_backend.py` usam `gpiozero.pins.mock` — validam
  wiring (mode certo → classe certa, escala de valor certa), **não são
  prova de que o hardware físico funciona**. Primeiro teste real é
  sempre em Pi de verdade.

---

## Rodando os testes

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```
