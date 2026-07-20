# 05 — Casos de Uso

> **Navegação:** [Visão Geral](01-visao-geral.md) | [C4 Diagrams](02-diagrama-c4.md) | [Fluxos](03-fluxos.md) | [Modelo de Dados](04-modelo-de-dados.md) | [Manutenção](06-manutencao-e-expansao.md)

## Atores

```mermaid
flowchart LR
    A([👤 Operador]) --- B["Usa o painel web\npara monitorar e controlar\no processo em tempo real"]
    C([👨‍💻 Desenvolvedor]) --- D["Instala, configura\ngerencia serviço\nadapta para novo domínio"]
    E([🤖 Tesseract Core]) --- F["Sistema externo\nEnvia comandos via MQTT\nRegistra LWT de failsafe"]
    G([⚙️ systemd]) --- H["Inicia bridge no boot\nReinicia em caso de falha\nGerencia ciclo de vida"]
```

---

## UC01 — Iniciar uma receita

**Ator**: Operador
**Pré-condição**: `recipe.yml` carregado com sucesso no boot; bridge em status `idle`, `finished` ou `aborted`.

```mermaid
flowchart LR
    A([Operador]) -->|"Aba Receitas\nClica ▶ ou Iniciar"| B{Engine em\nestado ativo?}
    B -- Não --> C[POST /api/recipe/start]
    B -- Sim --> D["Reinicia do zero\nmesmo comportamento"]
    C --> E["RecipeState:\nstatus = ramping\nstep_index = 0\nrecipe_started_at = now\nAlarmEvent: vessel_start"]
    D --> E
    E --> F([Receita em execução])
```

**Fluxo alternativo**: Receita já rodando — `start()` interrompe e reinicia do zero (não precisa abortar manualmente antes).

---

## UC02 — Pausar e retomar

**Ator**: Operador
**Pré-condição**: Receita em status `ramping` ou `holding`.

```mermaid
sequenceDiagram
    participant U as Operador
    participant P as Painel
    participant E as RecipeEngine
    participant H as Hardware

    U->>P: Clica ⏯ (pausar)
    P->>E: POST /api/recipe/pause
    E->>E: paused_from_status = status atual
    E->>E: hold_elapsed = now - hold_started_at (se holding)
    E->>H: apply_failsafe(todos is_risk=true)
    E->>E: status = paused_manual

    Note over U,H: Atuadores desligados — processo seguro

    U->>P: Clica ⏯ (retomar)
    P->>E: POST /api/recipe/resume
    E->>E: Se paused_from_status=holding:\n  hold_started_at = now - hold_elapsed\nSe paused_from_status=ramping:\n  step_started_at = now
    E->>E: status = holding ou ramping
    Note over E,H: Tempo de patamar preservado
```

---

## UC03 — Navegar entre etapas manualmente

**Ator**: Operador
**Pré-condição**: Receita em status `ramping` ou `holding`.

```mermaid
flowchart TD
    A([Operador]) --> B{Botão pressionado}
    B -->|"⏮ anterior"| C["skip_previous:\nstep_index > 0 → step_index--\nstep_index = 0 → reinicia a atual\nstatus = ramping\nfired_hop_alarm_keys = []"]
    B -->|"↺ reiniciar etapa"| D["reset_current_step:\nstatus = ramping\nstep_started_at = now\nfired_hop_alarm_keys = []"]
    B -->|"⏭ próxima"| E["skip_next:\nDesliga heater atual\nSe nova vasilha: vessel_end + vessel_start\nstep_index++\nstatus = ramping\nfired_hop_alarm_keys = []"]
    C --> F([Execução continua])
    D --> F
    E -->|"Era a última"| G([status = finished])
    E -->|"Não era a última"| F
```

---

## UC04 — Confirmar um alarme

**Ator**: Operador
**Pré-condição**: `pending_alarms` não vazio (banner âmbar visível + som tocando).

```mermaid
flowchart LR
    A([Operador]) -->|"Clica OK"| B["stopAlarmPlayback\n(cancela repetições futuras)"]
    B --> C["POST /api/recipe/alarms/id/ack\nRemove AlarmEvent da lista\nSalva recipe_state.json"]
    C --> D{Fila tem\nmais alarmes?}
    D -- Sim --> E["Exibe próximo\nInicia novo playback"]
    D -- Não --> F["Oculta banner\nSilêncio"]
```

**Regra de parada do som**: toca pelo número de repetições configurado (1-20) OU para no clique em OK, o que vier primeiro. Token de cancelamento garante que ciclos agendados em `setTimeout` não tocam depois do ack.

---

## UC05 — Cancelar receita

**Ator**: Operador
**Pré-condição**: qualquer status (no-op seguro em `idle`).

| | `abort()` | `pause()` |
|---|---|---|
| Failsafe aplicado | ✅ | ✅ |
| Estado preservado | ❌ (descarta) | ✅ (preserva hold_elapsed) |
| Como retomar | `start()` — reinicia do zero | `resume()` — de onde parou |
| Status final | `aborted` | `paused_manual` |

---

## UC06 — Recuperação após queda de energia

**Ator**: Sistema (automático) + Operador (confirmação)

```mermaid
sequenceDiagram
    participant OS as Pi OS / systemd
    participant E as RecipeEngine (construtor)
    participant H as Hardware
    participant P as Painel
    participant U as Operador

    OS->>E: Reinicia bridge (Restart=on-failure)
    E->>E: load(recipe_state.json)
    E->>E: status == ramping ou holding?
    Note over E: Sim → crash detectado no construtor
    E->>H: apply_failsafe(todos is_risk=true)
    E->>E: status = paused_after_crash

    P->>U: Banner VERMELHO:<br/>"Execução interrompida durante [rampa/patamar]"

    U->>U: Verifica fisicamente o equipamento
    U->>P: Clica Retomar
    P->>E: POST /api/recipe/resume
    E->>E: Reconstrói hold_started_at<br/>preservando tempo já decorrido
    E->>E: status = holding ou ramping
    Note over E,H: Tempo de patamar não perdido
```

---

## UC07 — Controlar atuador manualmente

**Ator**: Operador
**Pré-condição**: Device tem `role: actuator`.

```mermaid
flowchart LR
    A([Operador]) -->|"Aba Painel\nbotão liga/desliga"| B["POST /api/devices/id/command\n{value: true|false}"]
    B --> C{Receita ativa\nno mesmo device?}
    C -- Não --> D["DeviceRuntime.set_actuator\nbackend.write(pin, value)"]
    C -- Sim --> E["⚠️ Conflito!\nRecipeEngine e controle manual\ncompetindo pelo mesmo atuador"]
    E --> F["Último write vence\nsem lock de prioridade"]
    D --> G([Atuador responde])
    F --> G
```

**Regra**: Use controle manual só quando a receita não estiver ativa naquele device.

---

## UC08 — Diagnosticar GPIO com gpio_test.py

**Ator**: Desenvolvedor
**Motivação**: isolar se o problema é backend, pino, active_high ou hardware — antes de depurar no bridge completo.

```mermaid
flowchart TD
    A([Desenvolvedor\npython tools/gpio_test.py]) --> B["[4] Info backend\nConfirma qual backend GPIO está ativo\nEx: RPi.GPIO, lgpio, pigpio"]
    B --> C{Backend correto\npara o Pi?}
    C -- Não --> D["pip install RPi.GPIO\nou pip install lgpio\nou sudo pigpiod"]
    D --> A
    C -- Sim --> E["[1] Testar saída\nPede: pino BCM, active_high, duração"]
    E --> F{Relé respondeu\nfisicamente?}
    F -- Sim --> G["GPIO ok!\nProblema estava no bridge ou config"]
    F -- Não --> H{"active_high\ncorreto?"}
    H -- Não --> I["Alterar active_high\nno devices.yml e tentar de novo\nou testar com active_high=false"]
    H -- Sim --> J["[2] Diagnóstico rápido\nTesta múltiplos pinos em sequência\nIdentifica quais respondem"]
    J --> K["Hardware ou permissão\nsudo usermod -a -G gpio $USER"]
    I --> E
```

---

## UC09 — Instalar como serviço systemd

**Ator**: Desenvolvedor
**Pré-condição**: bridge instalado e funcionando via `python run_bridge.py`.

```mermaid
sequenceDiagram
    participant D as Desenvolvedor
    participant S as install_service.sh
    participant SD as systemd
    participant LXDE as LXDE Desktop

    D->>S: sudo bash tools/install_service.sh

    S->>S: Detecta SUDO_USER ou logname
    S->>D: "Usuário detectado: pi — Confirmar? [1] ou [2] digitar outro"
    D->>S: Escolha [1]

    S->>S: Detecta PROJECT_DIR (diretório do script)
    S->>S: Detecta PYTHON_BIN (.venv ou which python3)
    S->>S: Gera /etc/systemd/system/tesseract-bridge.service
    Note over S: User=pi, WorkingDirectory=..., FORCE_COLOR=1
    S->>SD: systemctl daemon-reload && enable
    S->>D: "Iniciar agora? [S/n]"
    D->>S: S
    S->>SD: systemctl start tesseract-bridge

    S->>D: "Criar autostart LXDE? [S/n]"
    D->>S: S
    S->>LXDE: ~/.config/autostart/tesseract-bridge-logs.desktop
    Note over LXDE: No próximo login: abre lxterminal<br/>com journalctl -fu tesseract-bridge --output=cat

    S->>D: Resumo com comandos úteis
```

---

## UC10 — Ver logs ao vivo

**Ator**: Desenvolvedor / Operador
**Pré-condição**: serviço instalado e rodando.

```mermaid
flowchart LR
    A([Usuário]) --> B{Como quer ver?}
    B -->|"Desktop LXDE\n(automático no boot)"| C["lxterminal abre sozinho\nmostra journalctl --output=cat\ncom cores ANSI do bridge"]
    B -->|"SSH / terminal"| D["bash tools/logs.sh"]
    D --> E{Opção?}
    E -->|"(padrão)"| F["logs ao vivo\n-n 50 + follow"]
    E -->|"--all"| G["toda a sessão\ndo serviço atual"]
    E -->|"--boot"| H["desde o último boot"]
    C --> I([Logs coloridos ao vivo])
    F --> I
    G --> I
    H --> I
```
