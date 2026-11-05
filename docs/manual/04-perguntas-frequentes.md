# 04 — Perguntas frequentes | versão 2.0.0

> [Primeiros passos](02-primeiros-passos.md) ·
> [Administração SQLite](13-administracao-sqlite.md) ·
> [Migração](12-sqlite-migracao.md)

## Por que o inventário e a Administração SQLite estão na mesma aba?

O **inventário** é a configuração **em execução**, em memória, e é
somente leitura. A **Administração SQLite** permite editar o cadastro
persistido, salvar rascunhos, validar e aprovar novas revisões. A
aprovação não aciona GPIO: somente um próximo boot seguro utiliza a
nova revisão. Não é uma ferramenta de execução livre de comandos SQL.

## Qual token devo informar?

O token gerado ou personalizado no setup. O .env pode usar ADMIN_TOKEN_B64
para serialização; informe o token original no formulário, não o Base64.
ADMIN_TOKEN simples continua compatível. A política local sem token exige
LOCAL_ADMIN explícito; [detalhes](18-credencial-administrativa.md).
Reinicie após alterar o token. O token é uma credencial da API
administrativa, **não** a senha do banco SQLite.

## O botão Desbloquear não funciona

Cheque se a credencial foi carregada pelo processo. Token curto é aceito,
com aviso no setup. Token incorreto retorna **401**; sem credencial nem
política local explícita, a administração retorna **503**. No modo local,
reabra a sessão para renovar CSRF e confira origem/Host de loopback. Não publique seu token em prints
ou logs. Verifique o console do navegador para erros de rede.
O token é mantido somente na memória da página após desbloqueio.

## Para que serve o arquivo .env?

Define infraestrutura, não receitas, GPIO ou PID:

```dotenv
TESSERACT_BRIDGE_DB=./data/private/bridge.sqlite3
TESSERACT_BRIDGE_STORAGE_MODE=orm
TESSERACT_BRIDGE_SIMULATION_ONLY=1
TESSERACT_BRIDGE_TEST_PANEL_PORT=8089
TESSERACT_BRIDGE_ADMIN_TOKEN=SEU_SEGREDO
```

`SIMULATION_ONLY=1` força o backend simulado, desativa MQTT e
escuta em `127.0.0.1` na porta de teste. Em Windows PowerShell não
é necessário usar `export`: `python-dotenv` carrega o arquivo.
Variáveis já definidas no sistema têm prioridade sobre o `.env`.

## O painel não abre no outro computador/celular

Em simulação isolada, o host é **127.0.0.1**, disponível somente na
própria máquina. Não é defeito da rede. Para abrir na LAN seria
necessário configurar outro modo e avaliar autenticação, HTTPS e
controle de acesso. **Não exponha o painel diretamente na Internet.**

Se estiver em produção homologada com host de LAN, confira a porta
via `python -m storage.cli status` e o firewall.

## Como verifico se a importação terminou corretamente?

Execute `python -m storage.cli status`. Confira o caminho do SQLite,
a contagem de dispositivos e receitas e a revisão. Na UI, verifique
Gerenciamento e Cadastro. A presença dos registros não comprova
sozinha a calibração e as ligações físicas: revise IDs, ROM IDs, GPIOs,
referências de receita e parâmetros antes de qualquer teste real.

## Aparece "Banco SQLite inexistente"

Confira `python -m setup.doctor` e o caminho configurado. Em clone novo,
conclua `python -m setup`; o banco é publicado ao final. Se já existe recibo,
use recuperação/backup, não gere um banco vazio para substituir o ausente.
`storage.cli init` permanece apenas para compatibilidade legacy.

## O importador rejeita pump_b1 com remote_control

Se `remote_control: true` não possui `state_topic`, o schema
recusa o cadastro. Mantenha a origem preservada; corrija uma cópia de trabalho ou use
`--disable-invalid-remote-control`, que **desliga** a permissão
remota no SQLite, mantém o arquivo antigo intacto e registra o ajuste.
Não invente tópicos nem contorne intertravamentos.

## Como adiciono ou escolho outra receita?

Use a aba **Cadastro**, duplicando uma receita (inclusive a protegida
`public:base`). Escolha a classificação **pública/privada** do
cadastro e selecione a receita para o próximo boot.

Na 2.0.0, os dois tipos ficam no mesmo SQLite. **Pública não implica
publicação automática no Git**. A troca da receita ativa exige
reiniciar o processo em segurança.

## Ajustei a potência mas a execução atual não mudou

O motor usa snapshot de parâmetros para cada execução. Salvar o perfil
térmico altera a **próxima execução iniciada**, não uma etapa já em
andamento. Alterações de hardware e calibração entram no próximo boot
seguro.

## Posso manter o Bridge antigo e o SQLite no mesmo Raspberry Pi?

Somente se o clone experimental estiver isolado, em
`TESSERACT_BRIDGE_SIMULATION_ONLY=1`, com MQTT desligado, host local
e porta diferente. **Nunca dois processos em modo real disputando
os mesmos GPIOs/atuadores.**

## Como diagnosticar sensor/atuador que não responde?

Confirme `backend_runtime` em `python -m storage.cli status`.
Na simulação nenhum GPIO é acionado. Em homologação real,
confira ROM ID (`python -m gpio.ds18b20_scan`), cabeamento,
alimentação, polaridade e fail-safe. Não bypass as proteções.
Para instruções de bancada veja [Calibração](11-calibracao-sensores.md)
e [Segurança](06-desligamento-emergencia.md).

## O sistema voltou em estado de queda ou emergência

O retorno seguro bloqueia as saídas. Verifique fisicamente conexões,
líquidos, resistências, bombas e sensores **antes** de confirmar qualquer
retomada manual. Nunca habilite retomada automática de atuadores após
falta de energia.

## O serviço do Raspberry Pi não inicia

Confira a venv com Python **3.9.x**, permissões em `data/private`,
variáveis de ambiente e logs do processo. O systemd e o watchdog devem
usar a porta correta e o usuário da instalação. Não instale a branch
experimental em substituição à principal sem homologação.

## Posso testar uma porta serial sem cadastrar dispositivo?

Sim. Use o monitor na Administração SQLite ou na configuração inicial vazia.
Liste portas do servidor ou informe COM3 / /dev/ttyUSB0, ajuste os parâmetros e
confirme o teste de abertura ou leitura. Não há envio de comandos. Veja o
[manual serial](../modules/serial-monitor/README.md).

## O teste CLI falha com No module named reusable

Atualize a branch. O clone mínimo do teste deve incluir setup/, shared_ui/ e
reusable/. A correção 2133f7e ajusta essa preparação; não copie só setup/ para
outra instalação. Confira também o [guia dos componentes](../modules/README.md).
