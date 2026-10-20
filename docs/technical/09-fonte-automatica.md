# Contrato de fonte automática v1

State topic preserva `value` e acrescenta `heat_source`: version 1, device_id,
boot_id (por fonte/processo), arm_token descartável, sequence crescente,
observed_at UTC, backend real/simulated, participation primary/auxiliary,
armed, lease_id, output_on, target, reason, fault, temperature_sensor,
temperature, controller_device, limits e external_protection independent_hardware.
Saída é lógica. Nenhuma confirmação física de gás/chama é inferida.

Comando no command_topic: `{"heating_control": {...}}`. Arm/renew exige version,
boot_id atual, issued_at UTC com atraso máximo 5 s/futuro 2 s, lease_id,
sequence inteira crescente, target. Arm exige arm_token atual e limites validados;
renew só estende autorização existente com mesmo alvo, nunca arma. Stop aceita
`{"heating_control":{"action":"stop"}}`; OFF genérico também desabilita.

Após expiração/stop, token muda. Boot novo invalida mensagens anteriores.
Autorização dura 10 s monotônicos a partir do recebimento. MQTT com QoS1,
retain=false; a recepção ignora comandos retidos para fontes protegidas.
Isso é proteção de repetição/acidente, não autenticação: use broker autenticado/ACL.

DeviceRuntime é dono único da saída: bloqueia ON genérico mesmo que alguém use
API local ou receita. `SourceControl` é máquina de estados pura, sem GPIO/rede.
O loop Bridge chama tick_sources depois de receita/TPC. Supervisor e encerramento
existentes mandam OFF para todos os atuadores, desabilitando todas as fontes.
Nenhuma exceção à proteção é oferecida por configuração de modo manual.

No Core, Device Manager valida identidade, sequência/boot, data e tipos antes de
persistir a observação. Publicar autorização não altera o cache observado.
BrewStation mantém autorizações em memória da aplicação, renovadas somente por
observações da fonte. Pausa/mudança de contexto, falha, fonte disarmada e telemetria
antiga removem a autorização e enviam stop de melhor esforço. HTTP e MQTT devem
estar no mesmo processo nesta versão; não existe coordenação distribuída.

Testes simulados abrangem arbítrio, proteção contra ON genérico, OFF imediato,
histerese, TTL, repetição, boot, datas, sensor inválido, sobretemperatura, recepção
MQTT, permissão/escopo HTTP e comandos explícitos do widget. Hardware/rede reais
não são certificados por esses testes. O corte externo não tem retorno de estado;
perda de chama/rearme após essa falha pertencem ao circuito independente.

## Validação desta entrega

Suíte completa do Bridge: 511 testes Python aprovados em backend simulado.
Fixture `tests/fixtures/heat_source_v1.json` idêntica nos dois repositórios,
confrontada com o publicador real e processada pelo adaptador MQTT do Core.
Comando gerado pelo Core aceito pelo Bridge, com ON e corte térmico OFF simulados.
Sem broker de rede, hardware real, Windows ou Raspberry Pi neste ambiente.
