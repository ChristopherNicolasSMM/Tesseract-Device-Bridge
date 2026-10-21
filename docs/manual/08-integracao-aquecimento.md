# Integração de aquecimento com o Tesseract

> Modo opcional posterior: [fonte automática protegida](09-fonte-automatica.md).
> As restrições de ausência de comandos abaixo descrevem a entrega 3.

Atualize o Bridge e o Tesseract para a entrega 3. A atualização é compatível com
comandos/sensores antigos. Não liga equipamentos automaticamente e não muda os
pontos ou a duração da janela de potência.

## Configuração

Declare `state_topic` no aquecedor com controle por janela:

```yaml
- id: mash_heater
  name: Resistência Mostura
  role: actuator
  subtype: digital
  command_topic: actuators/mash_heater/set
  state_topic: actuators/mash_heater/state
  hardware:
    pin: 17
    window_seconds: 10
    external_control_policy: local_only
  is_risk: true
  failsafe_value: false
```

Ajuste o pino/tópicos à instalação existente; o exemplo não é instrução de ligação.

| Política | Comportamento de comandos MQTT individuais |
|---|---|
| `manual_override` (padrão) | Mantém comportamento anterior: percentual arma override manual remoto; `null` libera o override para o controle local/repouso. |
| `local_only` | Bloqueia comandos de aquecimento e liberação remota; aceita somente OFF (0/false). Após OFF, o operador local libera o override quando apropriado. |

O árbitro local continua com prioridade: emergência/failsafe, manual, receita local,
repouso. A mudança entre failsafe/manual/receita/repouso realinha a janela como anteriormente;
variações de percentual dentro da mesma origem aguardam a próxima janela.
O painel local continua utilizável nas duas políticas. `local_only` vale apenas
para os atuadores de janela em que for configurado; não altera outros dispositivos.
A política é lida ao iniciar o Bridge; reinicie para aplicar mudanças no YAML.

## No Tesseract

Configure as duas aplicações no mesmo broker e `topic_prefix`.
Importe/reimporte os YAMLs pelo cadastro Bridge. Tópicos MQTT ausentes são preenchidos,
mas tópicos personalizados existentes não são substituídos. Na aba **Planta**, nos
mapeamentos do tanque, confira a função do aquecedor e, em **Aquecimento e água de
lavagem**, selecione **Controlador de aquecimento (telemetria Bridge)**. O nome da
função deve corresponder ao `id` do dispositivo no Bridge. Se configurou o Device
Manager manualmente, associe os mesmos `state_topic` e `command_topic` ao ator.

O widget mostra demanda antes do teto, teto, automático limitado, duty escolhido
pelo árbitro, duty da janela em andamento e saída lógica GPIO. Seleção e janela
podem ser diferentes por alguns segundos: isso é o comportamento acordado.
A origem identifica backend `real` ou `simulated` e receita local, manual local,
manual remoto, failsafe ou repouso. Esses dados não comprovam corrente elétrica,
potência efetivamente dissipada, presença de chama ou funcionamento da solenoide.

Para a regra da entrega 2 usar demanda do controlador, selecione origem **Receita
local do controlador Bridge**. O Bridge deve operar em backend real, sem override
manual/failsafe, e ter leitura recente. O alvo precisa coincidir com o do Tesseract
(tolerância 0,1 °C) e a temperatura com o sensor principal (0,5 °C). A seleção de
um controlador não inicia nem sincroniza receitas entre as aplicações.

Use relógios sincronizados. Mensagens retidas, repetidas, fora de ordem ou com data
inválida não renovam a telemetria de controle. Sem dados recentes, a regra bloqueia
pedidos e o painel informa indisponibilidade. O modo simulado serve para testar
o painel e não libera pedidos baseados em demanda do Bridge.

## Limites e validação local

Nenhum comando novo de aquecimento é emitido pelo widget. Solicitações continuam
sendo respostas manuais do operador. O fogareiro GLP continua manual; não há controle
de gás automático ou confirmação de proteções. Os mecanismos locais de emergência
continuam prevalecendo, mesmo se o Tesseract perder conexão.

Valide primeiro com backend simulado e broker de teste. Depois confira a telemetria
na instalação real com o operador, inclusive OFF, override local/remoto e failsafe.
Não é necessária migração no Bridge. No Tesseract esta entrega não adiciona migração;
mantenha aplicadas as migrações das entregas anteriores.


A operação remota de potência e bombas pode ser habilitada por equipamento.
Veja [controles remotos](10-controles-remotos.md).
