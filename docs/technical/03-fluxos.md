# 03 — Fluxos de Execução

> **Navegação:** [Visão Geral](01-visao-geral.md) | [C4 Diagrams](02-diagrama-c4.md) | [Modelo de Dados](04-modelo-de-dados.md) | [Casos de Uso](05-casos-de-uso.md) | [Manutenção](06-manutencao-e-expansao.md)

## Fluxo 1 — Boot do serviço systemd e seleção de backend GPIO

Mostra o que acontece desde o boot do Pi até o bridge estar pronto para receber comandos.

```mermaid
sequenceDiagram
    participant OS as Raspberry Pi OS
    participant SD as systemd
    participant BR as run_bridge.py
    participant LC as logging_config.py
    participant GPIO as RealGPIOBackend
    participant LXDE as LXDE Desktop

    OS->>SD: Boot completo (multi-user.target)
    SD->>BR: ExecStart (FORCE_COLOR=1)
    BR->>LC: setup_logging(debug=False)
    Note over LC: FORCE_COLOR=1 → usa cores mesmo sem TTY
    LC-->>BR: ColoredFormatter instalado no root logger

    BR->>GPIO: RealGPIOBackend()
    GPIO->>GPIO: _pick_pin_factory()
    Note over GPIO: Tenta: lgpio → RPi.GPIO → pigpio
    GPIO-->>BR: INFO: backend selecionado: RPi.GPIO

    BR->>BR: BridgeConfig.load(data/public/devices.yml)
    BR->>BR: data.load_active_recipe(config) se alguma receita disponível
    BR->>BR: DeviceRuntime → setup() de cada device
    BR-->>SD: Processo rodando (PID registrado)

    Note over SD: Restart=on-failure → reinicia se cair

    OS->>LXDE: Usuário faz login no desktop
    LXDE->>LXDE: Carrega ~/.config/autostart/
    LXDE->>LXDE: lxterminal --title="Tesseract Bridge — Logs"
    LXDE->>LXDE: journalctl -fu tesseract-bridge --output=cat
    Note over LXDE: Mostra logs coloridos ao vivo
```

## Fluxo 2 — Seleção de backend GPIO (detalhe)

```mermaid
flowchart TD
    A([RealGPIOBackend.__init__]) --> B{pin_factory\npassado explicitamente?}
    B -- Sim --> C[Usa o factory passado\nexemplo: MockFactory nos testes]
    B -- Não --> D[_pick_pin_factory]

    D --> E{lgpio disponível?\npip install lgpio}
    E -- Sim --> F["LOG INFO: backend selecionado: lgpio\nPi OS Bookworm / Pi 5"]
    E -- Não --> G{RPi.GPIO disponível?\npip install RPi.GPIO}
    G -- Sim --> H["LOG INFO: backend selecionado: RPi.GPIO\nRaspbian / Bullseye / Buster"]
    G -- Não --> I{pigpio disponível?\npip install pigpio + daemon}
    I -- Sim --> J["LOG INFO: backend selecionado: pigpio\nrequer pigpiod rodando"]
    I -- Não --> K["LOG WARN: nenhum backend explícito\ngpiozero usa default automático"]

    F --> L([setup chamado depois\nDigitalOutputDevice com active_high])
    H --> L
    J --> L
    K --> L
    C --> L

    L --> M{mode = output?}
    M -- Sim --> N["DigitalOutputDevice(pin,\n  active_high=active_high,\n  initial_value=False,\n  pin_factory=factory)"]
    M -- Não --> O{mode = pwm?}
    O -- Sim --> P["PWMOutputDevice(pin,\n  active_high=active_high,\n  frequency=pwm_frequency)"]
    O -- Não --> Q{mode = input_analog?}
    Q -- Sim --> R["driver_factory(pin,\n  address=address,\n  base_path=...)"]
    Q -- Não --> S[DigitalInputDevice]
```

## Fluxo 3 — Execução de receita (caminho feliz)

```mermaid
flowchart TD
    A([POST /api/recipe/start]) --> B["RecipeState: status=ramping\nstep_index=0\nrecipe_started_at=now\nAlarme: vessel_start disparado"]
    B --> C{tick — sensor >= target_temp?}
    C -- Não --> D["PID.compute(setpoint, temp, dt)\nTPC.set_duty_cycle(duty)\nTPC.should_be_on(now) → liga/desliga heater\nPublica estado dos sensores via MQTT"]
    D --> C
    C -- Sim --> E["status = holding\nhold_started_at = now"]
    E --> F{tick — elapsed >= hold_minutes × 60?}
    F -- Não --> G["Checa hop_alarms:\nse remaining ≤ minutes_remaining × 60\n→ AlarmEvent(hop_addition) disparado"]
    G --> F
    F -- Sim --> H{Última etapa?}
    H -- Não --> I["Desliga heater da vasilha atual\nSe nova vasilha ≠ atual:\n  AlarmEvent(vessel_end)\n  AlarmEvent(vessel_start)\nstep_index++\nfired_hop_alarm_keys=[]\nstatus=ramping"]
    I --> C
    H -- Sim --> J["Desliga tudo\nAlarmEvent(vessel_end)\nstatus=finished\ntotal_elapsed_seconds congelado"]
    J --> K([Receita concluída])
```

## Fluxo 4 — Recuperação de crash (queda de energia / kill -9)

```mermaid
flowchart TD
    A([Pi reinicia / bridge reinicia]) --> B["RecipeEngine.__init__\ncarrega recipe_state.json"]
    B --> C{status salvo é\nramping ou holding?}
    C -- Não → idle/finished/aborted --> D["Inicia normalmente\nestado preservado conforme salvo"]
    C -- Sim → crash detectado --> E["Crash detectado no construtor\nnão depende de signal handler\nfunciona mesmo em SIGKILL"]
    E --> F{status era holding?}
    F -- Sim --> G["hold_elapsed = now - hold_started_at\n(tempo já decorrido antes do crash)"]
    F -- Não --> H["hold_elapsed = 0"]
    G --> I
    H --> I["apply_failsafe em TODOS os\natuadores is_risk:true do devices.yml\n(segurança ampla — não só os da receita)"]
    I --> J["paused_from_status = status anterior\nhold_elapsed_seconds_at_pause = hold_elapsed\nstatus = paused_after_crash\nSalva recipe_state.json"]
    J --> K([Painel mostra banner vermelho])
    K --> L{Operador clica Retomar}
    L --> M{paused_from_status\nera holding?}
    M -- Sim --> N["hold_started_at = now - hold_elapsed\n(preserva tempo já contado)\nstatus = holding"]
    M -- Não --> O["step_started_at = now\nstatus = ramping"]
    N --> P([Execução retomada])
    O --> P
```

## Fluxo 5 — Failsafe MQTT (Tesseract Core cai)

```mermaid
sequenceDiagram
    participant T as Tesseract Core
    participant B as Broker MQTT
    participant D as Device Bridge
    participant W as FailsafeWatchdog
    participant H as Hardware físico

    T->>B: CONNECT<br/>LWT: {status:offline, failsafe_actuators:[...]}
    T->>B: PUBLISH status = online
    B->>D: status = online (repassa)
    Note over D,W: Operação normal<br/>Watchdog marca last_seen por device

    loop a cada poll_interval (2s)
        D->>W: check(now)
        W->>W: now - last_seen > failsafe_timeout_seconds?
        W-->>D: [] (nenhum timeout ainda)
    end

    Note over T: Tesseract cai (crash / rede / energia)
    B->>D: LWT: {status:offline, failsafe_actuators:[{command_topic, failsafe_value}]}

    Note over D: StatusTopicHandler.handle_message()
    D->>D: busca device por command_topic<br/>(não por external_id)
    D->>H: set_actuator(heater, false)
    D->>H: set_actuator(pump, false)

    Note over W: Mesmo sem LWT (ex.: bridge perde o broker)<br/>watchdog local cobre o gap
    W->>D: timeout: apply_failsafe(device_id)
    D->>H: failsafe_value aplicado
```

## Fluxo 6 — Ciclo de alarme (disparo → som → confirmação)

```mermaid
sequenceDiagram
    participant E as RecipeEngine
    participant S as RecipeState (JSON)
    participant P as Painel JS (poll 2.5s)
    participant U as Operador

    E->>S: _fire_alarm(type, label, now)<br/>AlarmEvent(id=N, type, label, fired_at)<br/>next_alarm_id++<br/>save()

    P->>E: GET /api/recipe/status
    E->>P: {..., pending_alarms: [{id, type, label, fired_at}]}

    Note over P: pending_alarms[0].id ≠ alarmBannerCurrentId
    P->>P: alarmBannerCurrentId = id<br/>showAlarmBanner(label, extra)<br/>startAlarmPlayback() → toca N vezes ou até OK

    P->>U: Banner âmbar pulsante + som

    alt Operador clica OK
        U->>P: click OK
        P->>P: stopAlarmPlayback()<br/>alarmBannerCurrentId = null
        P->>E: POST /api/recipe/alarms/{id}/ack
        E->>S: remove AlarmEvent(id)<br/>save()
    else Som esgota as N repetições
        P->>P: playback para sozinho<br/>banner permanece visível
        Note over P: Próximo poll vai ver o alarme ainda pendente<br/>mas não reinicia o som (mesmo id)
    end

    E->>P: {..., pending_alarms: [próximo ou []]}
    Note over P: Se próximo → showAlarmBanner + startPlayback<br/>Se [] → hideAlarmBanner
```

## Fluxo 7 — Diagnóstico GPIO com gpio_test.py

```mermaid
flowchart LR
    A([python tools/gpio_test.py]) --> B["RealGPIOBackend()\n_pick_pin_factory()"]
    B --> C{Menu principal}

    C -->|"[1] Testar saída"| D["Pede: pino BCM\nactive_high\nduração ou manual"]
    D --> E["backend.setup(pin, 'output', active_high)"]
    E --> F["backend.write(pin, True)\nAguarda / conta segundos"]
    F --> G["backend.write(pin, False)\nbackend.teardown(pin)"]
    G --> C

    C -->|"[2] Diagnóstico rápido"| H["Pede: lista de pinos\nactive_high\nduracao por pino"]
    H --> I["Para cada pino:\nsetup → write True → sleep → write False → teardown"]
    I --> J["Resumo: OK ✅ ou ERRO ❌"]
    J --> C

    C -->|"[3] Ler DS18B20"| K["Pede: pino BCM\naddress ROM\nintervalo"]
    K --> L["backend.setup(pin, 'input_analog',\ndriver='ds18b20', address)"]
    L --> M["Loop: backend.read(pin, address)\nPrinta [HH:MM:SS] XX.XX °C"]
    M -->|CTRL+C| C

    C -->|"[4] Info backend"| N["Mostra backend ativo\nExplica como trocar\nComandos raspi-gpio para teste sem Python"]
    N --> C

    C -->|"[5] Sair"| O([Fim])
```

## Fluxo 8 — Prioridade de controle de um atuador (failsafe > manual > receita > repouso)

`DeviceRuntime` é o dono único da escrita física em qualquer atuador que
o `RecipeEngine` também gerencia (heaters com `hardware.window_seconds`
via `tick_duty()`; bombas via `_apply_pumps()`) — nenhum dos dois
escreve direto no GPIO por conta própria, ambos passam por essa
resolução de prioridade. Isso evita a receita desfazer silenciosamente
um comando manual (heater) ou uma bomba "voltar sozinha" numa troca de
etapa (achado real, ver `_apply_pumps`/`has_manual_override`).

```mermaid
flowchart TD
    A([A cada tick / comando]) --> B{Failsafe\nsuspenso?}
    B -- Sim --> C["Força 0% / desligado\nSempre vence, sem exceção"]
    B -- Não --> D{Override manual\nativo?}
    D -- "Sim (heater: duty_enabled\nbomba: has_manual_override)" --> E["Aplica o valor manual\n(duty_percent ou True/False)"]
    D -- Não --> F{Receita ativa\nneste device?}
    F -- Sim --> G["Aplica o valor da receita\n(PID para heater, step.pumps\npara bomba)"]
    F -- Não --> H["Repouso (0% / desligado)"]
```

**Quem chama o quê:**

| Situação | Heater (`hardware.window_seconds`) | Bomba (sem controle de potência) |
|---|---|---|
| Painel: toggle Ligado/Desligado | `set_manual_enabled(id, bool)` | `set_manual_override(id, bool)` via `/command` |
| Painel: slider de % | `set_manual_duty_percent(id, valor)` — não arma sozinho | N/A |
| Receita pedindo controle | `set_pid_duty(id, valor)` a cada tick | `_apply_pumps()` — só se não houver override |
| Failsafe (local ou externo) | `apply_failsafe`/`apply_failsafe_external` — suspende e força 0% | Mesmo mecanismo — suspende e escreve `failsafe_value` |
| Retomada explícita (`resume()`) | `resume_all_suspended_overrides()` — TPC se resolve sozinho no próximo `tick_duty()` | Mesmo método — reescreve o GPIO explicitamente (bomba não tem loop contínuo) |

Retomada **nunca** acontece por reconexão de rede (watchdog de timeout,
status agregado do Tesseract voltando a `online`) — só por
`POST /api/recipe/resume`, ação explícita do operador.

## Fluxo 9 — Confirmação de acionamento automático de bomba (só bombas, não heaters)

Camada extra de segurança **só pra bombas**, entre "sem override" e
"aplica o valor da receita" do Fluxo 8: mesmo sem override manual, a
receita nunca liga uma bomba pela **primeira vez nesta execução** sem
aprovação explícita — evita energizar uma bomba com conexão fechada ou
errada sem ninguém checar. Heaters não têm essa camada (o operador já
vê o % antes de armar o interruptor manual, e a receita nunca liga um
heater "do nada" sem estar em `ramping`/`holding`).

```mermaid
flowchart TD
    A(["_apply_pumps() quer ligar\numa bomba (off -> on)"]) --> B{Tem override\nmanual?}
    B -- Sim --> C["Não mexe\n(override sempre vence, Fluxo 8)"]
    B -- Não --> D{Já foi confirmada\nnesta execução?}
    D -- Sim --> E["Liga normalmente\n(set_actuator + entra em _active_pumps)"]
    D -- Não --> F["Fica pendente\nNÃO liga sozinha"]
    F --> G{Operador decide\nno painel}
    G -- Confirmar --> H["confirm_pump_auto()\nvale pro resto desta execução"]
    G -- "Manter manual" --> I["decline_pump_auto()\n= set_manual_override(id, False)"]
    H --> E
```

**Escopo da confirmação** (`RecipeEngine._confirmed_pumps`/`_pending_confirmation`):

| Evento | Confirmação é mantida? |
|---|---|
| Troca de etapa (mesma execução) | Sim — não pergunta de novo |
| `pause()` → `resume()` manual | Sim — é a mesma execução continuando |
| `start()` (nova execução) | **Não** — reseta, nova checagem de segurança |
| Crash do processo (nova instância de `RecipeEngine`) | **Não** — mais seguro reconfirmar do que assumir que nada mudou fisicamente |

Deliberadamente **não persistido** em `recipe_state.json` — é o único
jeito de garantir a linha "crash reseta" sem precisar de um caso
especial na recuperação.

`RecipeEngine.pending_pump_confirmations` (exposto em
`GET /api/recipe/status`) alimenta o banner de aviso e o subcard da
bomba (estado visual "aguardando confirmação", com os botões
Confirmar/Manter manual) no painel.
