# Referência funcional ampliada — Device Bridge 2.0.0

Conteúdo técnico anteriormente reunido no README central. Para instalar ou migrar,
use o [manual consolidado](../manual/20-instalacao-migracao-2.0.0.md).
Os exemplos YAML/JSON descrevem formatos legados de importação; a configuração
operacional da versão 2.0.0 fica no SQLite.

## Armazenamento e versionamento

O banco fica em `data/private/*.sqlite3` ou no caminho declarado em
`TESSERACT_BRIDGE_DB`. Ele, seu backup e o arquivo `.env` **não entram
no Git**. Receitas com marcador `public:` e `private:` continuam
diferenciadas no banco, mas **não** são automaticamente compartilhadas ou
versionadas no Git.

Em uma instalação nova, o banco começa sem dispositivos ou receitas.
O painel permite configurar o inventário sem inicializar hardware. Para preservar a instalação anterior,
importe uma cópia consistente dos arquivos antigos; a origem não é
modificada. Não use os arquivos YAML/JSON legados como configurações
operacionais do novo runtime.

## Recursos físicos e integração

A arquitetura separa `gpio/`, `device_runtime.py`, `bridge.py`,
`recipe_engine/`, `panel/` e `storage/`. O núcleo conserva a lógica
de medição, alarmes, prioridades de atuação e fail-safe.

**Importante:** os exemplos antigos de YAML/JSON são formatos de
**importação e referência de schema**, não um procedimento de operação
na 2.0.0. A configuração física deve ser editada na Administração SQLite
e aplicada após revisão e reinício seguro.


---

## Hardware suportado

> **2.0.0:** os exemplos de YAML abaixo documentam o formato de dispositivos,
> porém a configuração persistida e aplicada pelo runtime é SQLite. Consulte
> [Administração SQLite](../../docs/manual/13-administracao-sqlite.md) para editar.


A configuração de exemplo (`data/public/devices.yml.example`) mapeia a [Interface
CLP CraftBeerPi da MAZZA Handmade](https://www.mazzahandmade.com.br/produtos/interface-clp-para-raspberrypi-automacao-cervejeira-craftbeerpi-brewpi1/)
para Raspberry Pi 4B+ — 13 saídas NPN 12V 500mA digital liga/desliga
(não é PWM de hardware: potência variável é feita por software via
time-proportioning, ver seção do motor de receita) e sensores DS18B20
em barramento 1-Wire compartilhado (GPIO4 por padrão, vários sensores
no mesmo pino, cada um identificado pelo `hardware.address` — endereço
ROM gravado de fábrica). Mas **nada no código depende dessa placa
específica** — qualquer Raspberry Pi com GPIO comum e sensores 1-Wire
funciona, só ajustando os pinos no `data/public/devices.yml`.

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

### Leitura de DS18B20 em thread de fundo (não bloqueia o painel)

Ler `w1_slave` no Linux dispara uma conversão nova no sensor a cada
chamada — o kernel bloqueia até o resultado sair, tipicamente
~750-950ms. Sem cache, um `/api/devices` com vários sensores DS18B20
(mostura, fervura, chiller) travava a requisição inteira por
N × ~800ms, deixando o painel visivelmente lento a cada poll.

`Ds18b20Reader` resolve isso com uma thread dedicada por sensor: a
primeira leitura é síncrona (só uma vez, no boot — nunca durante uma
requisição HTTP); depois disso, uma thread de fundo mantém o valor
sempre atualizado em cache, e `.value` nunca bloqueia. Dois parâmetros
opcionais em `hardware:` (por sensor, no `devices.yml`):

```yaml
hardware:
  pin: 4
  driver: ds18b20
  address: "28-0000071234ab"
  poll_interval_seconds: 1.0   # opcional, default 1.0 — intervalo entre leituras
  stale_after_seconds: 10.0    # opcional, default 10.0 — ver abaixo
```

Se as leituras em background começarem a falhar (CRC ruim — comum em
1-Wire por ruído elétrico —, ou sensor desconectado), a thread loga o
erro e mantém o último valor bom em cache, sem derrubar nada. Só
depois de `stale_after_seconds` sem NENHUMA leitura bem-sucedida é que
`.value` passa a levantar `Ds18b20ReadError` de verdade — evita tanto
"trava tudo a cada glitch" quanto "mostra um valor de 20 minutos atrás
pra sempre, calado".

---

## Motor de receita (`recipe_engine/`)

> **2.0.0:** a definição de receita mantém o modelo lógico abaixo, mas agora
> é armazenada no SQLite, não em `recipe.yml` nem em `receita.json`.


Máquina de estado **100% autônoma** — funciona com `mqtt.enabled: false`
e sem o Tesseract de pé, dirigida só pelo loop principal de
`bridge.py`. Cada `vessel` (vasilha — ou zona, tanque, o que o seu
domínio precisar) tem seu próprio `PidController`; cada `step` da
receita declara qual vasilha controla, o alvo (`target_temp`), quanto
tempo segurar (`hold_minutes`), quais atuadores extras ligar
(`pumps`), e opcionalmente alarmes de etapa (`hop_alarms`).

O `TimeProportioningController` (que traduz duty 0-100% em liga/desliga
dentro de uma janela) **não pertence mais ao motor de receita** — vive
em `DeviceRuntime`, um por atuador que declarar `hardware.window_seconds`
no `devices.yml` (não mais no `recipe.yml`). O motor só *pede* um duty
a cada tick (`DeviceRuntime.set_pid_duty()`); quem decide o valor
efetivo e escreve no GPIO é o `DeviceRuntime`, considerando também um
eventual override manual (painel ou comando MQTT individual) — ver
seção "Controle de potência por atuador" abaixo.

### Schema do `recipe.yml`

> O schema abaixo é o mesmo pra `data/public/receita_base.yaml` (raiz
> do arquivo YAML) e pro campo `"recipe"` de cada registro dentro de
> `data/{public,private}/receita.json` (só que em JSON em vez de
> YAML) — é o formato de "uma receita", independente de onde ela mora.

```yaml
name: "Pilsen Clássica"

vessels:
  - id: mash               # referência estável, usada em steps.vessel
    name: "Mostura"         # texto livre de exibição
    order: 0                 # ordem de exibição na UI (opcional)
    heater_device_id: mash_heater   # precisa ter hardware.window_seconds no devices.yml
    sensor_device_id: mash_tun_temp
    pid: { kp: 5.0, ki: 0.1, kd: 0.0 }

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
referenciar algo que não existe. `heater_device_id` também é validado
quanto a ter `hardware.window_seconds` declarado — sem isso, o device
não tem onde aplicar o duty do PID.

> **Campo removido**: `window_seconds` não é mais aceito em `vessels`
> (era duplicado com `devices.yml` e podia divergir). Se presente, é
> ignorado e emite `DeprecationWarning` — mova o valor pra
> `hardware.window_seconds` no `devices.yml` do `heater_device_id`.

### Comportamento de execução

- **Rampa (`ramping`)**: PID calcula a saída (0-100%) a cada tick e
  registra em `DeviceRuntime.set_pid_duty()`. Se não houver override
  manual ativo nem failsafe suspenso, `DeviceRuntime.tick_duty()`
  aplica esse duty via `TimeProportioningController` (liga/desliga
  dentro da janela — necessário porque a maioria dos relés de
  automação industrial/agrícola é liga/desliga simples, não PWM
  analógico). Transição pra `holding` assim que o sensor atinge
  `target_temp`.
- **Patamar (`holding`)**: o tempo só começa a contar a partir do
  instante em que o alvo foi atingido — nunca desde o início da
  etapa. O PID continua ativo durante o patamar, mantendo o alvo.
- **Atuadores extras (`pumps`)**: ligados/desligados conforme a lista
  de cada etapa, reavaliado a cada tick.
- **Avanço de etapa**: desliga o atuador principal da vasilha
  anterior, zera o duty do PID registrado em `DeviceRuntime` (evita
  herdar acúmulo de uma etapa não relacionada), aplica os atuadores
  extras da nova etapa imediatamente. Um override manual eventualmente
  ativo **não** é afetado pela troca de etapa — continua valendo até
  ser liberado explicitamente (ver seção abaixo).

### Controle de potência por atuador (override manual)

Qualquer atuador com `hardware.window_seconds` no `devices.yml` ganha,
além do duty automático de uma receita ativa, um **override manual**
de potência — via painel (slider no card do atuador) ou via
`command_topic` individual (`{"value": 40}` = 40%, `{"value": null}`
limpa o override). Prioridade resolvida a cada tick por
`DeviceRuntime` (dono único da escrita no GPIO desse atuador — nunca
duas fontes competindo pelo mesmo pino):

1. **Failsafe suspenso** — sempre vence, força 0%, independente de
   override ou receita.
2. **Override manual** — se ativo, vence o duty da receita. Sobrevive
   a troca de etapa; só some quando explicitamente liberado (painel:
   botão "Liberar controle"; MQTT: `{"value": null}`) ou quando um
   failsafe suspende temporariamente.
3. **Duty da receita** — se não houver override nem failsafe
   suspenso, e uma receita estiver `ramping`/`holding` naquela
   vasilha.
4. **Repouso (0%)** — nenhuma das anteriores.

Quando um failsafe suspende o override (abort/pause/crash/watchdog de
timeout/status agregado do Tesseract offline), ele só volta sozinho
quando a retomada é uma ação **explícita** do usuário
(`POST /api/recipe/resume`) — nunca por reconexão de rede, preservando
a decisão já registrada de "voltar a `status: online` nunca religa
nada sozinho" (ver seção de contrato MQTT).

```
POST /api/devices/<id>/duty          -> {"duty_percent": 40} só define o valor — NÃO liga sozinho
POST /api/devices/<id>/duty/enabled  -> {"enabled": true|false} liga/desliga o interruptor mestre
```

### Override manual de bombas e outros atuadores simples (sem controle de potência)

Atuadores liga/desliga puro que uma receita também gerencia automaticamente
(bombas, via `step.pumps`) têm o mesmo problema de prioridade que os
atuadores de potência tinham antes da seção acima — só que mais sutil:
`RecipeEngine._apply_pumps()` decide ligar/desligar comparando a lista
de pumps da etapa atual contra o **bookkeeping interno do próprio
motor** (`self._active_pumps`), nunca contra o estado físico real. Sem
um jeito de marcar "isto está sob controle manual", um comando manual
aplicado enquanto a receita está rodando pode ser desfeito
silenciosamente na próxima troca de etapa — o motor não sabe que a
realidade mudou.

`DeviceRuntime.set_manual_override()`/`has_manual_override()` resolvem
isso pra qualquer atuador sem `hardware.window_seconds`: definir um
override registra a intenção e escreve no GPIO imediatamente (exceto
se o device estiver com failsafe suspenso); `_apply_pumps()` consulta
`has_manual_override()` e nunca escreve num device sob override,
mesmo que ele apareça na lista de pumps de uma etapa. O endpoint
`POST /api/devices/<id>/command` (painel/API) passou a registrar o
override em vez de escrever cru — usado tanto pela grade "Atuadores"
quanto pelo controle de bomba dentro do card da vasilha da receita.

```
POST /api/devices/<id>/command  -> {"value": true} define e liga; {"value": null} libera pro automático
```

Mesma regra de segurança da seção anterior: failsafe sempre suspende
(e `resume_all_suspended_overrides()`, chamado só por
`RecipeEngine.resume()`, reaplica o valor manual armazenado — aqui,
diferente do controle de potência, a reaplicação precisa reescrever o
GPIO explicitamente, já que atuadores booleanos não têm um loop
contínuo como o `tick_duty()`).

### Confirmação de acionamento automático de bomba

Camada extra, só pra bombas: mesmo sem override manual, a receita
**nunca liga uma bomba pela primeira vez numa execução** sem aprovação
explícita do operador — evita energizar uma bomba com conexão fechada
ou errada sem ninguém checar antes. `RecipeEngine` mantém
`_confirmed_pumps`/`_pending_confirmation` (em memória, deliberadamente
**não** persistido em `recipe_state.json` — um crash real do processo
exige reconfirmação, por segurança; pause/resume manual, sendo a
mesma execução continuando, preserva a confirmação normalmente).

```
GET  /api/recipe/status                  -> inclui "pending_pump_confirmations": ["pump_b1", ...]
POST /api/recipe/pumps/<id>/confirm      -> deixa a receita controlar essa bomba pro resto da execução
POST /api/recipe/pumps/<id>/decline      -> mantém manual (= set_manual_override(id, False))
```

Ver [Fluxo 9](../../docs/technical/03-fluxos.md#fluxo-9--confirmação-de-acionamento-automático-de-bomba-só-bombas-não-heaters)
pro diagrama completo e a tabela de quando a confirmação é preservada
vs. resetada.

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

> Na 2.0.0, Gerenciamento inclui inventário (somente leitura) e Administração
> SQLite (token, rascunhos, validação, revisão aprovada, backup e auditoria).
> Ver [manual da administração](../../docs/manual/13-administracao-sqlite.md).


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

- ~~Sem lock de prioridade entre receita ativa e comando MQTT individual
  sobre o mesmo device~~ — **resolvido**: para atuadores com
  `hardware.window_seconds`, `DeviceRuntime` é o dono único da escrita
  no GPIO (failsafe > override manual > duty da receita > repouso, ver
  seção "Controle de potência por atuador"). Continua valendo sem
  prioridade formal para atuadores **sem** `window_seconds` (liga/desliga
  puro, ex.: bombas) — não é um problema prático porque não faz sentido
  uma receita e um comando manual disputarem uma bomba booleana do
  mesmo jeito que disputam um duty de potência.
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

> Os testes de infraestrutura e migração da 2.0.0 devem ser executados em
> ambiente isolado. Não trate a suíte completa ou a homologação física como
> aprovadas enquanto os resultados ainda não forem confirmados.


```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```


## Calibração individual e Python do Raspberry Pi

A operação GPIO real fica presa ao **Python 3.9.x em uma venv**. A aba **Configurações**
possui seções separadas de controle térmico e **calibração individual de sensores**,
com offsets salvos em `data/private`, leitura bruta preservada e aplicação no próximo
reinício. Veja o [manual de calibração](../../docs/manual/11-calibracao-sensores.md).

## Controle de temperatura configurável

A aba **Configurações** reúne a curva de potência automática da mosturação, alertas de excesso e o perfil independente de fervura. Ajustes locais são preservados e passam a valer na próxima execução. Veja o [manual de configurações](../../docs/manual/05-configuracoes-temperatura.md). As janelas de acionamento e as prioridades de controle permanecem as existentes.


## Desligamento de emergência

Falhas do controlador bloqueiam novos acionamentos, mandam OFF em todos os atuadores e abortam a receita. O DS18B20 não mascara erros com o último valor bom. Veja [comportamento, limites físicos e validação em bancada](../../docs/manual/06-desligamento-emergencia.md).


## Windows e Raspberry Pi

Os caminhos padrão de dados são ancorados na instalação, inclusive ao iniciar por outra pasta. Veja [caminhos, logs e comandos por ambiente](../../docs/manual/07-windows-raspberry-caminhos.md). Windows usa backend simulado; Raspberry Pi usa backend real.

### Integração de aquecimento — entrega 3

Telemetria de demanda, limites, janela e origem de controle no Tesseract, com política
opcional `local_only`. Consulte o [manual de integração](../../docs/manual/08-integracao-aquecimento.md).
Sem novas atuações automáticas de GLP.

Fonte automática protegida (principal/auxiliar), opcional e desabilitada no boot:
[manual de testes](../../docs/manual/09-fonte-automatica.md). Requer proteção externa de
chama e Tesseract atualizado; comece pelo exemplo com backend simulado.


### Potência e bombas no Mash Control

O opt-in `hardware.remote_control: true` habilita comandos explícitos de potência
manual/automática e bombas no widget Aquecimento do Tesseract. O PID, a janela e
o painel local permanecem no Bridge. Veja [ativação e validação](../../docs/manual/10-controles-remotos.md)
e [contrato v1](../../docs/technical/10-controle-dispositivos.md). Sem migration.
