# 01 — Visão Geral Técnica

## Propósito

O `tesseract-device-bridge` é o componente de hardware do ecossistema
Tesseract: roda num Raspberry Pi (ou qualquer Linux com GPIO), lê sensores,
aciona atuadores, executa automação de processo via PID + time-proportioning
e se conecta ao Tesseract Core via MQTT quando disponível.

Nasce com um caso de uso concreto — controle de mostura de cervejaria —
mas o núcleo é genérico: tudo que é específico de domínio vive em
`devices.yml` (mapeamento de hardware) e `recipe.yml` (processo a
automatizar), não no código.

## Dependências externas

| Pacote | Uso |
|---|---|
| `flask` | Painel web (API REST + SPA) |
| `paho-mqtt` | Cliente MQTT (conexão com broker, publicação de estado, recepção de comandos e LWT) |
| `gpiozero` | Abstração de GPIO no Raspberry Pi (backend real) |
| `PyYAML` | Carga e validação de `devices.yml` e `recipe.yml` |
| `pytest` | Suite de testes (260+ testes) |

Sem dependências externas de banco de dados — estado de execução de receita
é persistido em `recipe_state.json` (JSON plano).

## O que o bridge expõe

### Via HTTP (painel web em `http://<pi>:8088`)

```
GET  /api/status
GET  /api/devices
GET  /api/devices/<id>
POST /api/devices/<id>/command
POST /api/devices/<id>/simulate

GET  /api/recipe/status
GET  /api/recipe/definition
POST /api/recipe/start
POST /api/recipe/abort
POST /api/recipe/pause
POST /api/recipe/resume
POST /api/recipe/skip_next
POST /api/recipe/skip_previous
POST /api/recipe/reset_step
POST /api/recipe/alarms/<id>/ack
```

### Via MQTT (quando `mqtt.enabled: true`)

| Tópico | Direção | Conteúdo |
|---|---|---|
| `<prefix>/sensors/<id>/state` | Bridge → broker | Valor atual do sensor (float/bool) |
| `<prefix>/actuators/<id>/set` | broker → Bridge | Comando de atuador (`{"value": ...}`) |
| `<prefix>/system/tesseract/status` | broker → Bridge | LWT agregado do Tesseract (failsafe) |

## Documentos técnicos relacionados

- [02 — Diagrama C4](02-diagrama-c4.md)
- [03 — Fluxos de execução](03-fluxos.md)
- [04 — Modelo de dados (schemas YAML)](04-modelo-de-dados.md)
- [05 — Casos de uso](05-casos-de-uso.md)
- [06 — Manutenção e expansão](06-manutencao-e-expansao.md)
