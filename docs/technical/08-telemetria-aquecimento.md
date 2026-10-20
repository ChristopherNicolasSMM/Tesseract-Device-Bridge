# Telemetria de aquecimento — plano da entrega 3

Contrato versionado no state_topic do aquecedor; publicar demanda, limites, seleção
do árbitro, janela TPC e GPIO separados. Preservar a janela acordada e a prioridade
failsafe > manual > PID local > repouso. Política opcional local_only bloqueia
comandos MQTT diferentes de OFF; default manual_override mantém compatibilidade.
Tesseract recebe o estado como observação, nunca como confirmação de comando.
Testar sequência/boot/data, limites de potência, override, failsafe, simulação,
recepção ponta a ponta por mensagens e compatibilidade. Sem automação de GLP.

## Contrato implementado — `heating` versão 1

A publicação usa o `state_topic` existente, QoS 0 e `retain=false`. A raiz preserva
`value` (valor lógico lido no GPIO) e acrescenta `heating` para dispositivos com
`hardware.window_seconds`. Sensores continuam com `{"value": ...}`; atuadores sem
janela e com `state_topic` passam a publicar esse mesmo envelope simples.

| Campo | Significado |
|---|---|
| `version`, `device_id` | Versão 1, id estável do dispositivo (nome da função no importador). |
| `boot_id`, `sequence` | UUID por processo Bridge, sequência crescente por publicação de aquecedor. |
| `observed_at`, `backend` | Data UTC com fuso; `real` ou `simulated`, conforme configuração explícita. |
| `owner` | `local_recipe`, `local_manual`, `remote_manual`, `failsafe`, `idle`. |
| `external_policy` | `manual_override` ou `local_only`. |
| `demand_percent` | Demanda PID limitada a 0–100 antes do teto térmico; fervura usa sua demanda de perfil. Ausente quando indisponível. |
| `power_limit_percent` | Teto térmico da receita. |
| `automatic_percent` | Duty após o teto solicitado pela receita. |
| `selected_percent` | Duty selecionado pelo árbitro, podendo vir de override/failsafe. |
| `applied_window_percent` | Duty travado na janela TPC atual; pode diferir do selecionado até a virada. |
| `output_on`, `window_seconds` | Saída lógica lida, duração da janela. Não são medição elétrica. |
| `temperature`, `target`, `fault` | Contexto usado no cálculo e latch de emergência, quando existente. |

`PidController.last_demand_percent` registra a demanda sem chamar compute uma segunda
vez e sem mudar o anti-windup. `set_pid_duty(..., telemetry=...)` transporta o contexto
para o runtime; chamadas sem contexto limpam métricas anteriores (pausa/parada).
Valores não finitos de duty são rejeitados. O runtime permanece dono único do GPIO.
O loop publica após watchdog, receita e aplicação da janela. Publicar nunca executa
comando ou muda o controle. Sem MQTT, continua autônomo.

Fixture de contrato: `tests/fixtures/heating_telemetry_v1.json`, idêntica no Tesseract.
Testes confrontam o payload real do publicador com a fixture, inclusive seleção 60%
e janela ainda em 100%; validam origem manual remota/local, política e failsafe.
O receptor valida versão/id, sequência/boot e datas. Política no emissor Tesseract
é prevenção de comando; a autoridade continua no Bridge, que rejeita por conta própria.
Timestamps não são assinatura/autenticação. Configure autenticação/ACL do broker na
instalação; não há novo mecanismo de confiança ou confirmação física nesta entrega.

[Manual operacional](../manual/08-integracao-aquecimento.md).

## Validação registrada

491 testes Python do Bridge aprovados; 265 testes selecionados no Tesseract e 17
testes JS aprovados. Fixture comum e payload real do publicador processado pelo
adaptador MQTT do Tesseract verificados. Backend simulado, sem broker de rede ou
hardware real; validação Windows/Raspberry Pi permanece local. A publicação final
de failsafe antes da desconexão é de melhor esforço; perda de rede/processo não
assegura entrega. Frescor e failsafes locais continuam necessários.
