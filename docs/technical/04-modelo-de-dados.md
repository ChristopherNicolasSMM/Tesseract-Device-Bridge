# 04 — Modelo de Dados

O bridge não usa banco de dados relacional — o estado é mantido em dois
arquivos YAML de configuração e um JSON de estado de execução. Os diagramas
abaixo documentam os schemas desses arquivos usando notação ER para
explicitar as relações.

## Schema de `devices.yml`

```mermaid
erDiagram
    BridgeConfig {
        string backend "simulated | real"
    }
    MqttConfig {
        bool enabled
        string host
        int port
        string username
        string password
        string client_id
        string topic_prefix
        int reconnect_interval_seconds
    }
    PanelConfig {
        bool enabled
        string host
        int port
    }
    Device {
        string id "único no arquivo — referenciado por recipe.yml"
        string name "texto livre"
        string role "sensor | actuator"
        string subtype "temperature | digital | pwm | analog"
        string state_topic "sensores: tópico MQTT de publicação"
        string command_topic "atuadores: tópico MQTT de recepção"
        bool is_risk "true = incluso em failsafe automático"
        float failsafe_value "valor aplicado no failsafe"
        int failsafe_timeout_seconds "opcional — timeout local"
    }
    HardwareConfig {
        int pin
        string driver "opcional — ds18b20 para sensores 1-Wire"
        string address "ROM ID do sensor DS18B20 (obrigatório se driver=ds18b20)"
    }
    SimulatedConfig {
        float initial_value "valor inicial no backend simulado"
    }

    BridgeConfig ||--|| MqttConfig : "mqtt:"
    BridgeConfig ||--|| PanelConfig : "panel:"
    BridgeConfig ||--|{ Device : "devices: []"
    Device ||--|| HardwareConfig : "hardware:"
    Device ||--o| SimulatedConfig : "simulated: (opcional)"
```

### Regras de validação de `devices.yml`

| Regra | Detalhe |
|---|---|
| `id` único | Nenhum device pode ter o mesmo `id` — erro de config explícito |
| `pin` duplicado só se `driver: ds18b20` | Múltiplos sensores no mesmo pino 1-Wire são aceitos se cada um tiver `address` único |
| `address` obrigatório com `driver: ds18b20` | Sem `address`, o bridge não consegue distinguir sensores no barramento compartilhado |
| `failsafe_value` do tipo certo | Coercido no load pelo `failsafe_coercion.py` conforme `subtype` — `digital` → bool, `pwm`/`temperature` → float |
| `command_topic` obrigatório em actuators | Sensor não tem `command_topic`; actuator não tem `state_topic` |

---

## Schema de `recipe.yml`

```mermaid
erDiagram
    Recipe {
        string name "nome livre da receita"
    }
    Vessel {
        string id "referência estável — usada em Step.vessel"
        string name "texto livre de exibição"
        int order "opcional — ordem na UI (default: posição na lista)"
        string heater_device_id "FK para Device.id em devices.yml"
        string sensor_device_id "FK para Device.id em devices.yml"
        float window_seconds "janela de time-proportioning"
    }
    PidGains {
        float kp
        float ki
        float kd
    }
    Step {
        string vessel "FK para Vessel.id"
        float target_temp "alvo de temperatura (graus)"
        float hold_minutes "tempo de patamar após atingir target_temp"
        string label "opcional — texto de exibição na timeline"
    }
    HopAlarm {
        float minutes_remaining "contagem regressiva pro FIM do patamar"
        string label "texto do alarme exibido no banner"
    }

    Recipe ||--|{ Vessel : "vessels: []"
    Recipe ||--|{ Step : "steps: []"
    Vessel ||--|| PidGains : "pid:"
    Step ||--o{ HopAlarm : "hop_alarms: [] (opcional)"
    Step }|--|| Vessel : "vessel: (FK por id)"
    Vessel }|--|| Device : "heater_device_id (FK externa ao devices.yml)"
    Vessel }|--|| Device : "sensor_device_id (FK externa ao devices.yml)"
```

### Regras de validação de `recipe.yml`

| Regra | Detalhe |
|---|---|
| `vessels` é lista, não dict | Espelha convenção de `devices.yml`; `id` é a chave estável |
| `Vessel.id` único | `RecipeError` explícito se duplicado |
| `Step.vessel` deve existir em `vessels` | Validado no `Recipe.load()` |
| `heater_device_id`/`sensor_device_id` devem existir em `devices.yml` | Validação cruzada — falha cedo com mensagem clara |
| `hop_alarm.minutes_remaining <= hold_minutes` | Alarme que nunca dispararia é rejeitado |
| `hop_alarm.minutes_remaining >= 0` | Valor negativo é rejeitado |

---

## Schema de `recipe_state.json`

Estado de execução persistido em disco — sobrevive a `kill -9`.

```mermaid
erDiagram
    RecipeState {
        string recipe_name "nome da receita em execução (ou null)"
        string status "idle|ramping|holding|paused_manual|paused_after_crash|finished|aborted"
        int step_index "índice da etapa atual em Recipe.steps"
        float step_started_at "epoch (null se idle)"
        float hold_started_at "epoch — quando target_temp foi atingido (null fora de holding)"
        float hold_elapsed_seconds_at_pause "segundos de patamar já decorridos antes da pausa"
        string paused_from_status "status anterior à pausa (ramping ou holding)"
        float recipe_started_at "epoch do início da execução (null se idle)"
        float total_elapsed_seconds_frozen "snapshot do decorrido total ao terminar/cancelar"
        int next_alarm_id "contador monotônico para IDs únicos de alarme"
    }
    AlarmEvent {
        int id "ID único monotônico"
        string type "vessel_start | vessel_end | hop_addition"
        string label "texto exibido no banner"
        float fired_at "epoch do disparo"
    }

    RecipeState ||--o{ AlarmEvent : "pending_alarms: [] (alarmes nao confirmados)"
    RecipeState ||--o{ string : "fired_hop_alarm_keys: [] (chaves step_index:alarm_index)"
```
