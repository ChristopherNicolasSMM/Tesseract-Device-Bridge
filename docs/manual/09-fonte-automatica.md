# Fonte automática protegida — testes

O Bridge aceita uma fonte digital liga/desliga, principal ou auxiliar, sob
habilitação explícita no widget do Tesseract. Não habilita dispositivos existentes.

[Manual completo, parâmetros e procedimento no Tesseract](https://github.com/ChristopherNicolasSMM/Tesseract/blob/main/docs/manual/09-aquecimento-automatico.md).

Use primeiro o exemplo [devices.heating-source.yml.example](../../data/public/devices.heating-source.yml.example),
com `backend: simulated`, em Windows/Linux:

```text
python run_bridge.py data/public/devices.heating-source.yml.example
```

Requer broker configurado e Tesseract atualizado, com HTTP e MQTT no mesmo processo.
O painel isolado `run_panel.py` não executa o controlador. Os pinos do exemplo são
marcadores de simulação, não um esquema elétrico. Em Raspberry Pi, configure driver,
endereço, pino e polaridade reais antes de selecionar `backend: real`.

## Declaração de capacidade

A fonte deve ter role actuator, subtype digital, `is_risk: true`,
`failsafe_value: false`, tópicos de comando e estado. No `hardware`:

```yaml
heating_source:
  participation: auxiliary
  temperature_sensor: mash_temp
  controller_device: mash_heater
  external_flame_cutoff: true
```

`mash_temp` e `mash_heater` são ids existentes no mesmo Bridge; o controlador deve
ter janela/PID e contexto de receita local fresco. Para principal, use
`participation: primary`; `controller_device` é dispensável, pois o controle usa
alvo da sessão Tesseract e sensor local. Sem PWM/janela na saída da solenoide.
`external_control_policy: local_only` pode continuar na resistência controladora,
mas não deve ser colocado na solenoide, cujo contrato é outro.

**Proteção externa de chama:** o circuito informado pelo operador corta a corrente
da válvula normalmente fechada e aciona sirene. Deve impedir reabertura após falha
até rearme manual no próprio circuito. O software não recebe retorno de chama nem
verifica se esse circuito está instalado. O YAML declara o pré-requisito; não o cria.

O GPIO ON não comprova corrente, abertura da válvula ou ignição. Parada web é
solicitação por rede. Corte físico independente é necessário para emergência;
processo morto, SO travado ou relé colado não são cobertos pela lógica Python.

## Comportamento

- Habilitação não persistida; boot, autorização e token evitam repetição/rearme.
- Autorização renovável de 10 s, medida por relógio monotônico. Expiração é aplicada
  no próximo tick do loop; com período padrão, acrescente até cerca de 2 s.
- Principal usa temperatura. Auxiliar também exige demanda PID local, mesmo alvo e
  sem override/failsafe, com contexto atualizado nos últimos 5 s.
- Condição sustentada e tempo mínimo desligado precedem ON. OFF não espera janela
  da resistência nem tempo mínimo ligado. Corta em alvo −0,5 °C; +3 °C é emergência geral.
- OFF, falha, pausa/encerramento ou mudança de contexto exigem nova habilitação;
  a perda de rede/servidor expira a autorização enquanto o Bridge continua rodando.
- ON genérico via painel/MQTT/receita é bloqueado para a fonte protegida. OFF genérico
  continua permitido e desabilita o controle. Comandos retidos nessa fonte são ignorados.

Configuração de limites está no formulário da fonte no Tesseract. Valores de fábrica:
demanda 80%, distância 2 °C, condição sustentada 10 s, mínimo desligado 30 s.
O modo não regula intensidade de fervura nem controla vapor/recipiente pressurizado.

[Contrato técnico](../technical/09-fonte-automatica.md).
