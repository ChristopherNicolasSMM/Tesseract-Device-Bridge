# Contrato device_control v1

Opt-in `hardware.remote_control: true` em atuadores digitais/janela com tópicos.
Proibido em fontes protegidas `heating_source`. Sem opt-in o protocolo legado
continua disponível; booleano ON legado de janela corresponde a 100%, não 1%.

Publicação de estado sem retain contém `value`, `heating` quando aplicável e
`control`. A fixture `tests/fixtures/device_control_v1.json` é compartilhada com
o Bridge. `control` contém versão, device_id, boot_id, sequência, observed_at UTC,
backend, kind (`power`/`pump`), política, saída lógica, override, porcentagem
armazenada, proprietário, falha, confirmação pendente e resultado do último comando.

Comando no tópico individual, QoS1, sem retain:

```json
{"device_control":{"version":1,"request_id":"UUID novo","boot_id":"boot recebido","issued_at":"2026-10-21T12:00:00+00:00","action":"power_prepare","value":40}}
```

Ações: `power_prepare`, `power_enable`, `power_release`, `power_off`, `pump_set`
(booleano), `pump_release`, `pump_confirm`, `pump_decline`. O Bridge rejeita versão,
boot e parâmetros inválidos; idade máxima 5 s/futuro 2 s. Guarda os últimos 512
identificadores para não repetir operações de QoS1. Duplicatas não alteram o estado.
Confirmações de bomba exigem solicitação pendente. OFF de potência mantém override
0%; a janela normal continua sendo a autoridade do acionamento. Erros de IO
continuam seguindo o desligamento global do runtime.

O Core valida identidade, sequência, data, tipos, enums e limites antes de guardar
`runtime.bridge_control`. Nenhuma migration. Telemetria retida/repetida/inválida não
renova observação. O serviço de comando não altera cache nem leitura observada;
resultado `applied` confirma processamento lógico, não energização física.

BrewStation limita a rota à planta, tanque, controlador selecionado ou bombas
mapeadas, exige `brew_sessions.update`, e usa somente a API pública do Device
Manager. Renderização/polling não envia comandos. Fontes de gás mantêm a API
protegida existente. MQTT deve usar as ACLs/autenticação da instalação; este
contrato não implementa autenticação criptográfica própria.

Ciclo de sessão/receita e parâmetros térmicos permanecem locais nesta entrega.
Ver o [manual de operação](../manual/10-controles-remotos.md).
