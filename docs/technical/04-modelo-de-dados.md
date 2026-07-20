# 04 — Modelo de Dados

> **Navegação:** [Visão Geral](01-visao-geral.md) | [C4 Diagrams](02-diagrama-c4.md) | [Fluxos](03-fluxos.md) | [Casos de Uso](05-casos-de-uso.md) | [Manutenção](06-manutencao-e-expansao.md)

O bridge não usa banco de dados relacional. O estado é mantido em:
- **`devices.yml`** — mapeamento de hardware (editado uma vez, raramente muda)
- **`recipe.yml`** — definição do processo (editado por receita)
- **`recipe_state.json`** — estado de execução em tempo real (escrito pelo bridge a cada transição)

Os diagramas abaixo usam notação ER para explicitar as relações entre entidades.

---

## MER — `devices.yml`

```mermaid
erDiagram
    BridgeConfig {
        string backend "simulated | real — nunca autodetectado"
    }
    MqttConfig {
        bool enabled "false = sem cliente MQTT nenhum"
        string host "hostname ou IP do broker"
        int port "default 1883"
        string username "null = sem autenticação"
        string password "null = sem autenticação"
        string client_id "identificador único no broker"
        string topic_prefix "prefixo de todos os tópicos ex: brewery"
        int reconnect_interval_seconds "intervalo entre tentativas de reconexão"
    }
    PanelConfig {
        bool enabled "false = sem servidor web"
        string host "0.0.0.0 = aceita de qualquer IP da rede"
        int port "default 8088"
    }
    Device {
        string id "único — referenciado por recipe.yml e pelo broker"
        string name "texto livre de exibição no painel"
        string role "sensor | actuator"
        string subtype "temperature | digital | pwm | analog"
        string state_topic "sensores: tópico MQTT de publicação do valor"
        string command_topic "atuadores: tópico MQTT de recepção de comandos"
        bool is_risk "true = incluído no failsafe automático (LWT + watchdog)"
        float failsafe_value "valor aplicado em failsafe (coercido pelo subtype)"
        int failsafe_timeout_seconds "opcional — timeout local em segundos"
    }
    HardwareConfig {
        int pin "número BCM do pino GPIO"
        string driver "opcional — ds18b20 para sensores 1-Wire"
        string address "ROM ID do DS18B20 ex: 28-0000071234ab (obrigatório se driver=ds18b20)"
        bool active_high "opcional, default true — true: HIGH=ligado (NPN/MAZZA), false: LOW=ligado (relé active-low)"
        int pwm_frequency "opcional, default 100Hz — só mode=pwm"
    }
    SimulatedConfig {
        float initial_value "valor inicial no backend simulado (bancada/testes)"
    }

    BridgeConfig ||--|| MqttConfig : "mqtt:"
    BridgeConfig ||--|| PanelConfig : "panel:"
    BridgeConfig ||--|{ Device : "devices: []"
    Device ||--|| HardwareConfig : "hardware:"
    Device ||--o| SimulatedConfig : "simulated: (opcional)"
```

### Regras de validação de `devices.yml`

| Campo | Regra | Erro |
|---|---|---|
| `id` | Único em todo o arquivo | `ConfigError: id duplicado` |
| `pin` | Único, **exceto** quando `driver: ds18b20` + `address` único | `ConfigError: pino duplicado` |
| `address` | Obrigatório quando `driver: ds18b20` | `ConfigError: driver 'ds18b20' requer hardware.address` |
| `active_high` | Deve ser bool (`true`/`false`), **nunca string** (`'false'`) | `ConfigError: deve ser booleano` |
| `failsafe_value` | Coercido pelo `subtype`: `digital`→bool, `pwm`/`temperature`→float | `ConfigError` em tipo incompatível |
| `command_topic` | Obrigatório em `actuator`, proibido em `sensor` | `ConfigError` |
| `state_topic` | Obrigatório em `sensor`, opcional em `actuator` | `ConfigError` |

### active_high: quando usar cada valor

```
MAZZA Handmade (saídas NPN):
  GPIO → Base NPN → HIGH no pino → transistor conduz → relé fecha → carga liga
  active_high: true  ← HIGH = ligado (default, pode omitir)

Módulo relé "azul" do AliExpress (optoacoplador invertido):
  GPIO → Optoacoplador → LOW no pino → relé fecha → carga liga
  active_high: false  ← LOW = ligado
```

---

## MER — `recipe.yml`

```mermaid
erDiagram
    Recipe {
        string name "nome livre da receita ex: Pilsen Clássica"
    }
    Vessel {
        string id "referência estável — usada em steps.vessel"
        string name "texto livre de exibição ex: Mostura"
        int order "opcional — ordem de exibição na UI (default: posição na lista)"
        string heater_device_id "FK para Device.id (devices.yml)"
        string sensor_device_id "FK para Device.id (devices.yml)"
        float window_seconds "janela de time-proportioning em segundos"
    }
    PidGains {
        float kp "ganho proporcional"
        float ki "ganho integral (anti-windup por clamping)"
        float kd "ganho derivativo"
    }
    Step {
        string vessel "FK para Vessel.id"
        float target_temp "temperatura alvo em graus Celsius"
        float hold_minutes "tempo de patamar depois de atingir target_temp"
        string label "opcional — texto exibido na timeline do painel"
    }
    HopAlarm {
        float minutes_remaining "contagem regressiva pro FIM do patamar (convenção cervejeira)"
        string label "texto do alarme ex: Lúpulo Amargor - 30g Magnum"
    }
    StepPump {
        string device_id "FK para Device.id (actuator na role)"
    }

    Recipe ||--|{ Vessel : "vessels: [] (lista, não dict)"
    Recipe ||--|{ Step : "steps: []"
    Vessel ||--|| PidGains : "pid:"
    Step ||--o{ HopAlarm : "hop_alarms: [] (opcional)"
    Step ||--o{ StepPump : "pumps: [] (opcional)"
    Step }|--|| Vessel : "vessel: (FK por id)"
    Vessel }|--|| Device : "heater_device_id (FK externa)"
    Vessel }|--|| Device : "sensor_device_id (FK externa)"
    StepPump }|--|| Device : "device_id (FK externa)"
```

### Regras de validação de `recipe.yml`

| Campo | Regra | Erro |
|---|---|---|
| `vessels` | Lista (não dict) — `id` é a chave estável | `RecipeError: campo vessels` |
| `Vessel.id` | Único dentro da receita | `RecipeError: id duplicado` |
| `Step.vessel` | Deve existir em `vessels[].id` | `RecipeError: vessel não declarada` |
| `heater_device_id` | Deve existir em `devices.yml` | `RecipeError: não existe no devices.yml` |
| `sensor_device_id` | Deve existir em `devices.yml` | `RecipeError: não existe no devices.yml` |
| `pumps[]` | Cada id deve existir em `devices.yml` | `RecipeError: pump não existe` |
| `hop_alarm.minutes_remaining` | `≥ 0` e `≤ hold_minutes` | `RecipeError: negativo` ou `nunca dispararia` |

### Ciclo de vida da validação

```mermaid
flowchart LR
    A[Recipe.load] --> B[yaml.safe_load]
    B --> C[Recipe.from_dict\nvalida estrutura]
    C --> D[Vessel.from_dict\npara cada vessel]
    D --> E[PidGains\nkp ki kd]
    C --> F[Step.from_dict\npara cada step]
    F --> G[HopAlarm.from_dict\npara cada alarme]
    C --> H[recipe.validate\nbridge_config]
    H --> I[vessel.validate_against\nverifica device_ids]
    H --> J[step.validate_against\nverifica vessel ids\ne pump ids]
    J --> K[hopAlarm.validate_against\nverifica minutes_remaining ≤ hold_minutes]
    I --> L([Recipe pronta])
    K --> L
```

---

## MER — `recipe_state.json`

Estado de execução persistido em disco. Sobrevive a `kill -9` e quedas de energia. Carregado pelo construtor do `RecipeEngine` na inicialização — se o status for `ramping` ou `holding`, crash recovery é disparado automaticamente.

```mermaid
erDiagram
    RecipeState {
        string recipe_name "nome da receita em execução (null = idle)"
        string status "idle | ramping | holding | paused_manual | paused_after_crash | finished | aborted"
        int step_index "índice da etapa atual em Recipe.steps (0-based)"
        float step_started_at "epoch Unix do início da etapa atual (null = idle)"
        float hold_started_at "epoch Unix quando target_temp foi atingido (null fora de holding)"
        float hold_elapsed_seconds_at_pause "segundos de patamar decorridos antes da pausa (preservado em resume)"
        string paused_from_status "status anterior à pausa: ramping ou holding"
        float recipe_started_at "epoch Unix do início de toda a execução (null = idle)"
        float total_elapsed_seconds_frozen "snapshot do tempo total ao terminar ou cancelar"
        int next_alarm_id "contador monotônico — nunca reutilizado, evita ambiguidade de id"
    }
    AlarmEvent {
        int id "ID único monotônico"
        string type "vessel_start | vessel_end | hop_addition"
        string label "texto exibido no banner do painel"
        float fired_at "epoch Unix do disparo"
    }
    FiredHopAlarmKey {
        string key "formato: step_index:alarm_index — zerado quando a etapa reinicia"
    }

    RecipeState ||--o{ AlarmEvent : "pending_alarms: [] (confirmados saem da lista)"
    RecipeState ||--o{ FiredHopAlarmKey : "fired_hop_alarm_keys: [] (evita duplo disparo)"
```

### Transições de status

```mermaid
stateDiagram-v2
    [*] --> idle

    idle --> ramping : start()
    ramping --> holding : sensor >= target_temp
    holding --> ramping : avança para próxima etapa (mesma ou outra vasilha)
    holding --> finished : última etapa concluída

    ramping --> paused_manual : pause()
    holding --> paused_manual : pause()
    ramping --> paused_after_crash : crash recovery no construtor
    holding --> paused_after_crash : crash recovery no construtor

    paused_manual --> ramping : resume() (paused_from_status=ramping)
    paused_manual --> holding : resume() (paused_from_status=holding)
    paused_after_crash --> ramping : resume() (paused_from_status=ramping)
    paused_after_crash --> holding : resume() (paused_from_status=holding)

    ramping --> aborted : abort()
    holding --> aborted : abort()
    paused_manual --> aborted : abort()
    paused_after_crash --> aborted : abort()
    finished --> ramping : start() (reinicia do zero)
    aborted --> ramping : start() (reinicia do zero)
```
