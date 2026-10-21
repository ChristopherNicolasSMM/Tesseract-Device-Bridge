# Potência e bombas do Bridge no Mash Control

Esta entrega acrescenta controles ao widget **Aquecimento**, preservando o PID,
curva de limitação, janela de potência, prioridades, confirmação de bombas e
painel local do Device Bridge. Não exige `db upgrade`.

## Habilitação por equipamento

Atualize os dois projetos e reinicie os serviços. No `devices.yml` do Bridge,
acrescente `remote_control: true` somente à resistência e às bombas que deseja
operar pelo Tesseract. Preserve pinos, tópicos, limites e failsafes existentes.

```yaml
# Fragmento do hardware de uma resistência existente
hardware:
  pin: 17  # use o pino já configurado na sua instalação
  window_seconds: 10  # preserve a janela existente
  external_control_policy: manual_override
  remote_control: true
```

Em uma bomba digital, basta acrescentar `remote_control: true` ao hardware
existente. `external_control_policy` pertence apenas aos controles por janela.
Sem a opção nova, permanecem os comandos antigos. `local_only` continua bloqueando
ajustes, habilitação e liberação remotos da resistência, permitindo OFF.
**Não aplique `remote_control` à solenoide de gás**: fontes com `heating_source`
continuam usando a autorização protegida própria.

No Tesseract:

1. Confira broker, prefixo e tópicos de comando/estado iguais nas duas aplicações.
2. Em Device Manager, cada função deve corresponder exatamente ao `id` do Bridge,
   com um único ator ativo correspondente. Não é necessário apagar os cadastros.
3. Em Planta → tanque → mapeamentos, associe resistência e bombas ao tanque.
   Use os papéis **Atuador de aquecimento principal** e **Bomba 1–4**.
4. Em **Aquecimento e água de lavagem**, selecione a resistência no campo
   **Controlador de aquecimento (telemetria Bridge)** e salve.
5. Adicione/abra o widget **Aquecimento** desse tanque no dashboard. Os controles
   aparecem após receber o novo contrato do Bridge. Para operar, o usuário precisa
   de permissão `brew_sessions.update`.

## Operação

| Comando | Efeito no Bridge |
|---|---|
| Definir % | Prepara a potência manual; se o manual já estiver habilitado, altera sua porcentagem. |
| Habilitar manual | Habilita o override com a porcentagem armazenada. |
| Liberar para automático | Desabilita o override; a receita local retoma, se houver. Sem receita, repouso. |
| Desligar / manter 0% | Habilita override de 0%, impedindo retomada pelo PID até liberação consciente. |
| Ligar/desligar bomba manual | Usa a mesma prioridade manual do painel local. |
| Liberar bomba para receita | Remove o override, permitindo à receita local decidir. |
| Autorizar bomba na receita | Confirma a primeira utilização solicitada pela receita. |
| Manter desligada | Recusa a solicitação e mantém override OFF. |

Selecionar automático **não inicia nem sincroniza receitas**. Nesta etapa, carregue
e inicie a receita no Bridge; a sessão do Tesseract ainda tem ciclo independente.
O alvo exibido pelo Tesseract não altera o alvo do PID local. Confira ambos.

O widget informa responsável pelo controle, backend real/simulado, ON/OFF lógico e
último comando aceito/rejeitado. “Enviado” significa publicação MQTT; “aceito”
significa processamento pelo Bridge. Nenhum deles mede corrente, fluxo ou chama.
Mudanças de porcentagem conservam o comportamento da janela já acordado.

Comandos exigem telemetria de até 5 segundos, relógios sincronizados e MQTT
conectado. Mensagens retidas, antigas, repetidas ou de um boot anterior não
acionam equipamentos. O painel local continua disponível. Os controles genéricos
de ON/OFF são substituídos por estes comandos para equipamentos habilitados;
o OFF legado continua aceito sem atualizar visualmente o estado antes da leitura.

## Validação em bancada

Em backend simulado, confirme: definir 40% sem habilitar; habilitar manual;
liberar para receita; manter 0%; bomba manual ON/OFF/liberação; confirmação e
recusa de primeira utilização; bloqueio `local_only`; perda MQTT e leitura antiga;
falha de sensor com todas as saídas OFF. Depois valide no equipamento com os
procedimentos e proteções locais existentes. Os testes automatizados desta
entrega usam simulação; não substituem validação física no Raspberry Pi.

## Próximas etapas

- Vincular sessão/receita/etapa entre Tesseract e Bridge, com início, pausa,
  retomada, aborto, reconexão e identificação inequívoca da execução.
- Expor parâmetros térmicos e fábrica no Tesseract com leitura, validação e
  confirmação; preservar a regra de aplicação na próxima execução.
- Completar comparação de alarmes, navegação de etapas e recursos de diagnóstico,
  sem retirar as funções locais já validadas no Bridge.
