# 02 — Diagramas C4

> **Navegação:** [Visão Geral](01-visao-geral.md) | [Fluxos](03-fluxos.md) | [Modelo de Dados](04-modelo-de-dados.md) | [Casos de Uso](05-casos-de-uso.md) | [Manutenção](06-manutencao-e-expansao.md)

## Nível 1 — Contexto

Mostra os atores externos e como o bridge se encaixa no ecossistema.

```mermaid
C4Context
    title Contexto — Tesseract Device Bridge

    Person(user, "Operador", "Acompanha e controla o processo via painel web no celular ou computador")
    Person(dev, "Desenvolvedor", "Instala, configura devices.yml e recipe.yml, gerencia o serviço systemd")

    System(bridge, "Tesseract Device Bridge", "Raspberry Pi — lê sensores, aciona atuadores, executa automação de processo (PID + receita). Roda como serviço systemd, abre terminal de logs no boot do LXDE.")

    System_Ext(tesseract, "Tesseract Core", "Servidor Flask — gestão de receitas, RBAC, histórico. Comunica via MQTT.")
    System_Ext(broker, "Broker MQTT", "Mosquitto ou equivalente — intermediário entre Tesseract e Bridge")
    System_Ext(hardware, "Hardware físico", "Sensores DS18B20 (1-Wire), relés NPN (MAZZA / equivalente)")
    System_Ext(systemd, "systemd", "Gerenciador de serviços do Linux — inicia o bridge no boot e reinicia em caso de falha")

    Rel(user, bridge, "Acessa o painel web", "HTTP :8088, rede local")
    Rel(dev, bridge, "Instala, configura, monitora logs", "SSH / terminal LXDE")
    Rel(dev, systemd, "sudo systemctl ...", "CLI")
    Rel(systemd, bridge, "Inicia / reinicia", "ExecStart, Restart=on-failure")
    Rel(bridge, broker, "Publica estado / recebe comandos", "MQTT paho-mqtt")
    Rel(tesseract, broker, "Envia comandos / registra LWT", "MQTT")
    Rel(broker, bridge, "Repassa comandos e status", "MQTT")
    Rel(bridge, hardware, "Lê sensores / aciona atuadores", "GPIO gpiozero + 1-Wire")
```

## Nível 2 — Container

Mostra os componentes internos do bridge e suas responsabilidades.

```mermaid
C4Container
    title Container — Tesseract Device Bridge (dentro do Raspberry Pi)

    Person(user, "Operador")
    System_Ext(broker, "Broker MQTT")
    System_Ext(hardware, "Hardware físico")
    System_Ext(journal, "journald (systemd)", "Captura stdout/stderr do processo")

    Container(logging, "LoggingConfig", "Python — logging_config.py", "ColoredFormatter: cores ANSI por nível (DEBUG/INFO/WARN/ERROR). Ativo via TTY ou FORCE_COLOR=1 (serviço). Formato: [HH:MM:SS] NIVEL modulo: msg")
    Container(panel, "Painel Web", "Flask + JS (SPA)", "Interface de controle — 3 abas: Painel, Gerenciamento, Receitas")
    Container(api, "API REST", "Flask Blueprint — api.py", "Endpoints /api/* para devices e receita")
    Container(bridge_core, "Bridge", "Python — bridge.py", "Loop principal: publica sensores, watchdog de timeout, tick do motor de receita a cada poll_interval")
    Container(runtime, "DeviceRuntime", "Python — device_runtime.py", "Ponte config ↔ backend: lê sensores, escreve atuadores, aplica failsafe")
    Container(recipe_engine, "RecipeEngine", "Python — recipe_engine/", "PID + time-proportioning por vasilha, máquina de estado ramp/hold, alarmes, crash recovery")
    Container(gpio_backend, "GPIOBackend", "Python — gpio/", "Abstração de hardware. Seleção automática: lgpio → RPi.GPIO → pigpio. Drivers: DS18B20 (1-Wire)")
    Container(mqtt_client, "MqttClient", "Python — mqtt_client.py + failsafe_watchdog.py", "Wrapper paho-mqtt + watchdog de timeout local por device")

    Rel(user, panel, "Acessa", "HTTP")
    Rel(panel, api, "Usa", "")
    Rel(api, bridge_core, "Consulta / comanda", "")
    Rel(api, recipe_engine, "start/pause/skip/ack", "")
    Rel(bridge_core, runtime, "publish_sensor_states / apply_failsafe", "")
    Rel(bridge_core, mqtt_client, "start / stop", "")
    Rel(bridge_core, recipe_engine, "tick(now) a cada poll_interval", "")
    Rel(runtime, gpio_backend, "read() / write()", "")
    Rel(mqtt_client, broker, "subscribe / publish", "TCP")
    Rel(mqtt_client, bridge_core, "on_command / on_status callbacks", "")
    Rel(gpio_backend, hardware, "GPIO + 1-Wire", "")
    Rel(logging, journal, "stdout com FORCE_COLOR=1", "ANSI codes preservados pelo journald")
    Rel(bridge_core, logging, "getLogger()", "cross-cutting")
    Rel(recipe_engine, logging, "getLogger()", "cross-cutting")
    Rel(gpio_backend, logging, "getLogger()", "cross-cutting")
```

## Nível 3 — Componente: RecipeEngine

Zoom no componente de maior complexidade interna.

```mermaid
C4Component
    title Componente — RecipeEngine

    Container_Ext(bridge_core, "Bridge (loop principal)", "Chama tick(now) a cada poll_interval (default 2s)")
    Container_Ext(runtime, "DeviceRuntime", "Lê sensores / escreve atuadores")
    Container_Ext(state_file, "recipe_state.json", "Persistência em disco — sobrevive a kill -9 e quedas de energia")

    Component(engine, "RecipeEngine", "engine.py", "Coordena toda a execução: transições ramp→hold→advance, disparo de alarmes, crash recovery no construtor (detecta status ativo em recipe_state.json sem depender de signal handlers)")
    Component(pid, "PidController", "pid.py", "PID clássico (Kp/Ki/Kd) com anti-windup por clamping. dt sempre recebido por parâmetro — nunca lê o relógio internamente (testável sem sleep real)")
    Component(tpc, "TimeProportioningController", "time_proportioning.py", "Traduz duty cycle 0-100% em pulsos liga/desliga dentro de uma janela fixa (window_seconds). Necessário porque relés NPN são digital — não suportam PWM analógico")
    Component(state, "RecipeState", "state.py", "Dataclass: status, step_index, hold_started_at, pending_alarms[], fired_hop_alarm_keys[], recipe_started_at, total_elapsed_seconds_frozen")
    Component(models, "Recipe / Vessel / Step / HopAlarm", "models.py", "Schema YAML: validação cruzada com devices.yml no Recipe.load(). Vessels como lista (id + name + order). HopAlarm em contagem regressiva pro fim do patamar")

    Rel(bridge_core, engine, "tick(now) a cada 2s", "")
    Rel(engine, pid, "compute(setpoint, current_value, dt)", "instância por vasilha")
    Rel(engine, tpc, "set_duty_cycle(duty) / should_be_on(now)", "instância por vasilha")
    Rel(engine, runtime, "get_state(sensor_id) / set_actuator(id, value)", "")
    Rel(engine, state, "salva a cada transição de estado", "")
    Rel(state, state_file, "save() / load()", "JSON")
    Rel(engine, models, "recipe.steps / recipe.get_vessel(id)", "")
```

## Nível 3 — Componente: GPIOBackend (real)

Zoom na seleção de backend e driver de sensor.

```mermaid
C4Component
    title Componente — RealGPIOBackend

    Container_Ext(runtime, "DeviceRuntime", "Chama setup() / read() / write() / teardown()")
    System_Ext(hw_gpio, "GPIO físico", "/dev/gpiomem ou /dev/gpiochip0")
    System_Ext(hw_1wire, "Barramento 1-Wire", "/sys/bus/w1/devices/<address>/w1_slave")

    Component(real_be, "RealGPIOBackend", "gpio/real_backend.py", "Implementação sobre gpiozero. Seleção automática de pin factory: lgpio → RPi.GPIO → pigpio. Suporta active_high configurável. Log do backend selecionado no boot.")
    Component(pick_factory, "_pick_pin_factory()", "gpio/real_backend.py", "Tenta lgpio, depois RPi.GPIO, depois pigpio. Retorna o primeiro disponível ou None (fallback gziozero default). Log INFO com o backend escolhido.")
    Component(ds18b20, "Ds18b20Reader", "gpio/ds18b20_driver.py", "Lê /sys/bus/w1/devices/<address>/w1_slave, valida CRC, retorna float em °C. base_path injetável para testes (usa tmp_path com arquivo w1_slave fake)")
    Component(gpio_test, "gpio_test.py", "tools/gpio_test.py", "Script interativo standalone: testa pino de saída, diagnóstico rápido de múltiplos pinos, leitura de sensor DS18B20, info do backend. Sem precisar de devices.yml.")

    Rel(runtime, real_be, "setup(pin, mode, **kwargs)", "active_high, driver, address, pwm_frequency")
    Rel(real_be, pick_factory, "chama no __init__", "")
    Rel(real_be, ds18b20, "mode='input_analog', driver='ds18b20'", "")
    Rel(pick_factory, hw_gpio, "tenta conectar", "lgpio / RPi.GPIO / pigpio")
    Rel(ds18b20, hw_1wire, "open(w1_slave)", "filesystem")
    Rel(gpio_test, real_be, "usa diretamente", "diagnóstico isolado")
```
