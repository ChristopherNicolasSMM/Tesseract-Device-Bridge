# 02 — Diagrama C4

## Nível 1 — Contexto

Mostra os atores externos que interagem com o bridge e como ele se encaixa
no ecossistema maior.

```mermaid
C4Context
    title Contexto — Tesseract Device Bridge

    Person(user, "Operador", "Acompanha e controla o processo via painel web no celular ou computador")

    System(bridge, "Tesseract Device Bridge", "Raspberry Pi — lê sensores, aciona atuadores, executa automação de processo (PID + receita)")

    System_Ext(tesseract, "Tesseract Core", "Servidor Flask — gestão de receitas, RBAC, histórico. Comunica via MQTT.")
    System_Ext(broker, "Broker MQTT", "Mosquitto ou equivalente — intermediário de mensagens entre Tesseract e Bridge")
    System_Ext(hardware, "Hardware físico", "Sensores DS18B20 (temperatura), relés NPN (aquecedores, bombas) — interface MAZZA Handmade ou equivalente")

    Rel(user, bridge, "Acessa o painel web", "HTTP (porta 8088, rede local)")
    Rel(bridge, broker, "Publica estado dos sensores / recebe comandos", "MQTT (paho-mqtt)")
    Rel(tesseract, broker, "Envia comandos / registra LWT de failsafe", "MQTT")
    Rel(broker, bridge, "Repassa comandos e status do Tesseract", "MQTT")
    Rel(bridge, hardware, "Lê sensores / aciona atuadores", "GPIO (gpiozero) + 1-Wire")
```

## Nível 2 — Container

Mostra os componentes internos do bridge e como se relacionam.

```mermaid
C4Container
    title Container — Tesseract Device Bridge (dentro do Raspberry Pi)

    Person(user, "Operador")
    System_Ext(broker, "Broker MQTT")
    System_Ext(hardware, "Hardware físico")

    Container(panel, "Painel Web", "Flask + JS (SPA)", "Interface de controle manual e monitoramento — 3 abas: Painel, Gerenciamento, Receitas")
    Container(api, "API REST", "Flask Blueprint", "Endpoints /api/* que expõem estado de devices e receita, recebem comandos do operador")
    Container(bridge_core, "Bridge", "Python — bridge.py", "Orquestra todos os componentes: loop principal, publicação MQTT, watchdog de timeout, tick do motor de receita")
    Container(runtime, "DeviceRuntime", "Python — device_runtime.py", "Ponte entre a configuração (devices.yml) e o backend GPIO — lê sensores, escreve atuadores, aplica failsafe")
    Container(recipe_engine, "RecipeEngine", "Python — recipe_engine/", "Motor de processo: PID + time-proportioning por vasilha, máquina de estado ramp/hold, alarmes, crash recovery")
    Container(gpio_backend, "GPIOBackend", "Python — gpio/", "Abstração de hardware: SimulatedBackend (testes/bancada) ou RealBackend (gpiozero em Pi real) + drivers de sensor (DS18B20)")
    Container(mqtt_client, "MqttClient", "Python — mqtt_client.py + failsafe_watchdog.py", "Wrapper paho-mqtt: conexão, assinatura, despacho por tópico, watchdog de timeout local")

    Rel(user, panel, "Acessa", "HTTP")
    Rel(panel, api, "Usa", "Chamadas de função")
    Rel(api, bridge_core, "Consulta e comanda", "")
    Rel(api, recipe_engine, "start/pause/skip/ack", "")
    Rel(bridge_core, runtime, "publish_sensor_states / apply_failsafe", "")
    Rel(bridge_core, mqtt_client, "start/stop", "")
    Rel(bridge_core, recipe_engine, "tick() a cada poll_interval", "")
    Rel(runtime, gpio_backend, "read() / write()", "")
    Rel(mqtt_client, broker, "MQTT subscribe/publish", "TCP")
    Rel(mqtt_client, bridge_core, "on_command / on_status (callbacks)", "")
    Rel(gpio_backend, hardware, "GPIO + 1-Wire", "")
```

## Nível 3 — Componente (RecipeEngine)

Zoom no componente mais complexo — o motor de processo.

```mermaid
C4Component
    title Componente — RecipeEngine

    Container_Ext(bridge_core, "Bridge (loop principal)", "Chama tick() a cada poll_interval")
    Container_Ext(runtime, "DeviceRuntime", "Lê sensores / escreve atuadores")
    Container_Ext(state_file, "recipe_state.json", "Persistência em disco — sobrevive a kill -9")

    Component(engine, "RecipeEngine", "engine.py", "Coordena toda a execução: transições de estado, delegação para PID/TPC, disparo de alarmes, crash recovery no construtor")
    Component(pid, "PidController", "pid.py", "PID clássico (Kp/Ki/Kd) com anti-windup por clamping. dt sempre explícito — não lê relógio.")
    Component(tpc, "TimeProportioningController", "time_proportioning.py", "Traduz duty cycle (0-100%) em liga/desliga dentro de uma janela de tempo fixa — necessário pois os relés são digital, não PWM analógico")
    Component(state, "RecipeState", "state.py", "Dataclass serializável: status, step_index, hold_started_at, pending_alarms, fired_hop_alarm_keys, etc.")
    Component(models, "Recipe / Vessel / Step / HopAlarm", "models.py", "Schema de receita: validação cruzada contra devices.yml no load()")

    Rel(bridge_core, engine, "tick(now) a cada poll", "")
    Rel(engine, pid, "compute(setpoint, current_value, dt)", "por vasilha")
    Rel(engine, tpc, "set_duty_cycle() / should_be_on(now)", "por vasilha")
    Rel(engine, runtime, "get_state(sensor_id) / set_actuator(id, value)", "")
    Rel(engine, state, "salva a cada transição", "")
    Rel(state, state_file, "save() / load()", "JSON")
    Rel(engine, models, "recipe.steps / recipe.get_vessel()", "")
```
