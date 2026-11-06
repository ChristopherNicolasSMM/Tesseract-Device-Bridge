# Bombas: controle local, receita e MQTT

As bombas digitais usam liga/desliga, sem porcentagem de velocidade. No cadastro
analisado, `pump_b1` usa GPIO19 e `pump_b2` GPIO13. Em backend `simulated`, a saída
é apenas simulada; a ligação física depende de backend real e configuração válida.

## Estado e comando têm funções diferentes

Com `topic_prefix: brewery`, esta configuração é válida:

| Dispositivo | Campo | Tópico configurado | Tópico completo no broker |
| --- | --- | --- | --- |
| pump_b1 | state_topic | actuators/pump_1/state | brewery/actuators/pump_1/state |
| pump_b1 | command_topic | actuators/pump_b1/set | brewery/actuators/pump_b1/set |
| pump_b2 | state_topic | actuators/pump_2/state | brewery/actuators/pump_2/state |
| pump_b2 | command_topic | actuators/pump_b2/set | brewery/actuators/pump_b2/set |

O nome do tópico não precisa repetir o ID, mas o cliente Tesseract/MashControl
precisa usar esses endereços completos. Não inclua o prefixo novamente no campo:
`resolve_topic` sempre acrescenta `topic_prefix + '/'`. A grafia é literal;
`actuators` e `actuadores`, por exemplo, são tópicos diferentes.

O próprio Bridge publica em `state_topic` o JSON com `value` e, quando o remoto
está habilitado, o bloco `control`: ID, proprietário do controle, confirmação
pendente, falhas e resultado do último comando. A publicação usa QoS0, sem retain.
Não é preciso criar previamente o tópico no broker; são necessários broker e ACLs
adequados. `value` é a saída lógica conhecida pelo Bridge, sem comprovação de fluxo
ou de funcionamento mecânico da bomba.

No material revisado, `mqtt.enabled` estava `false`: não há comunicação MQTT até
habilitá-la e configurar o broker. O tópico é válido no código; isso não comprova
conectividade, permissões ou acionamento físico.

## Manual e automático

- **Manual:** `pump_set` com `value: true|false` fixa uma decisão manual. Enquanto
  houver override, a receita não modifica a bomba.
- **Liberar para receita:** `pump_release` remove o override; a receita decide
  nos próximos ticks conforme a etapa ativa. Liberar não significa ligar.
- **Automático:** a lista `pumps` da etapa pede as bombas desejadas. Na primeira
  ativação automática de cada bomba por execução, o motor pede confirmação.
  `pump_confirm` autoriza; `pump_decline` mantém um override desligado.
- **Proteções:** emergência, suspensão por failsafe e watchdog podem prevalecer
  sobre a intenção manual/automática. Reconectar não autoriza religamento sozinho.

Com `hardware.remote_control: true`, o acionamento remoto usa o envelope
`device_control`, versão 1, com `request_id` único, `boot_id` da telemetria atual e
`issued_at` com fuso e horário recente. `action` recebe uma das ações acima. Envie
no `command_topic`, sem retain. Um simples `true` no tópico de estado não liga a
bomba; no modo gerenciado, o ON legado também não substitui o protocolo explícito.
Os comandos devem vir de um cliente compatível com esse contrato.
