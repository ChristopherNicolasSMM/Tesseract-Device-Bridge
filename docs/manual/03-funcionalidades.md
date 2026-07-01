# 03 — Funcionalidades

## Aba Painel

Lista todos os sensores e atuadores configurados em `devices.yml`, com
atualização automática a cada poucos segundos.

**Sensores**: exibem o valor atual (temperatura em graus Celsius, ou
ligado/desligado para sensores digitais).

**Atuadores**: exibem o estado atual e têm um botão de controle manual —
útil para testar o equipamento antes de uma brassagem ou acionar algo
manualmente durante o processo (ex.: ligar a bomba brevemente para
recircular).

⚠️ Se uma receita estiver rodando, o controle manual e o motor de receita
podem entrar em conflito sobre o mesmo atuador. Use o controle manual só
quando a receita não estiver ativa naquele equipamento.

---

## Aba Gerenciamento

Tabela com a lista completa de devices configurados — nome, tipo (sensor ou
atuador), subtipo, e tópicos MQTT. Útil para verificar se o `devices.yml`
foi carregado corretamente.

---

## Aba Receitas

É aqui que acontece a brassagem. A aba só aparece funcional se um `recipe.yml`
estiver configurado.

### Status da receita

O cabeçalho mostra o nome da receita e uma etiqueta colorida com o status:

| Etiqueta | Cor | Significado |
|---|---|---|
| Parada | Cinza | Receita ainda não foi iniciada |
| Subindo | Âmbar | Sistema aquecendo até a temperatura alvo da etapa atual |
| Em patamar | Verde | Temperatura alvo atingida, contando o tempo de patamar |
| Pausada | Cinza | Você pausou manualmente |
| Pausada (queda) | Vermelho | Sistema reiniciou no meio da execução — ver seção de Recuperação |
| Concluída | Verde | Todas as etapas terminaram |
| Cancelada | Cinza | Você cancelou |

### Barra de controles

```
⏮  ↺  ⏯  ⏭
```

| Botão | Ação |
|---|---|
| `⏮` | Volta para a etapa anterior (ou reinicia a atual se já está na primeira) |
| `↺` | Reinicia a etapa atual do zero, sem mudar de etapa |
| `⏯` | Inicia / Pausa / Retoma — o sistema decide o que fazer conforme o estado atual |
| `⏭` | Avança para a próxima etapa imediatamente, ignorando temperatura e tempo |

**Cronômetro grande**: mostra o tempo restante quando estiver em patamar
(contagem regressiva), ou o tempo decorrido desde o início da rampa quando
estiver subindo a temperatura.

**Linha de tempo total**: tempo total decorrido desde o início da brassagem /
tempo total previsto (soma de todos os patamares configurados).

### Medidores de vasilha

Um medidor circular por vasilha configurada na receita. O anel laranja preenche
conforme a **potência aplicada** naquele momento — não é decoração, é um
indicador real de o quanto o aquecedor está sendo acionado pelo sistema de
controle. Na vasilha ativa:

- Temperatura atual no centro do anel
- Temperatura alvo logo abaixo
- Chip de bomba em verde quando a bomba está ligada

Vasilhas fora da etapa atual ficam acinzentadas com "aguardando".

### Timeline de etapas

Barra horizontal com uma bolinha por etapa. Etapas concluídas ficam em
cobre sólido, a etapa atual fica destacada (âmbar durante subida, verde
durante patamar), e as futuras mostram o alvo e o tempo de patamar.

### Gráfico ao vivo

Temperatura real (linha laranja sólida) vs. temperatura alvo (linha
tracejada cinza) dos últimos ~6 minutos. O gráfico reinicia quando o sistema
avança para uma nova vasilha.

---

## Alarmes

### Banner de alarme

Quando o momento de um alarme chega (ex.: "faltam 60 minutos para o fim da
fervura"), um banner âmbar aparece no topo da aba Receitas com o texto do
alarme e um botão **OK**. Um som também toca automaticamente.

Se houver mais de um alarme pendente (ex.: a fervura terminou e o alarme de
lúpulo ainda não foi confirmado), o contador "+ N alarme(s) na fila" aparece
abaixo do texto principal. Os alarmes são mostrados um por vez, na ordem em
que foram disparados.

Clique em **OK** para confirmar o alarme atual e avançar para o próximo (ou
fechar o banner se não houver mais).

### Tipos de alarme

| Tipo | Quando dispara |
|---|---|
| Início de vasilha | Quando o sistema começa a trabalhar em uma vasilha nova |
| Final de vasilha | Quando o sistema termina todas as etapas de uma vasilha |
| Adição programada | No momento configurado em `hop_alarms` da etapa (ex.: lúpulo) |

### Configuração de som

Botão **⚙️ Alarmes** no canto superior direito da aba Receitas. Opções:

- **Beep simples** — curto e discreto
- **Sirene** — dois tons alternados, mais chamativo
- **Campainha dupla** — dois bipes seguidos
- **Som personalizado** — clique em "Upload" e selecione um arquivo de áudio
  do seu computador (MP3, WAV, OGG etc.). O arquivo fica salvo no seu
  navegador — não vai pro servidor e não some quando você fechar a aba.

**Repetições**: número de vezes que o som toca antes de parar sozinho
(1 a 20). O som também para se você clicar em "OK" antes de atingir
o limite. Default: 3 repetições.

---

## Recuperação após queda de energia

Se o Raspberry Pi reiniciar no meio de uma brassagem (queda de energia,
travamento), o sistema detecta automaticamente que o processo foi
interrompido, desliga todos os atuadores de segurança (aquecedores, bombas),
e exibe um **banner vermelho** na aba Receitas:

> ⚠️ Execução interrompida — o processo encerrou durante [a rampa / o patamar].
> Failsafe já aplicado em todos os atuadores de risco. Retome de onde parou
> quando estiver pronto.

Antes de clicar em **Retomar**, verifique fisicamente se o equipamento está
em condições seguras de continuar. O sistema **nunca retoma sozinho** — só
ao seu clique explícito.

Se a queda ocorreu durante um patamar, o tempo já decorrido é preservado —
você não perde os minutos que já passaram.
