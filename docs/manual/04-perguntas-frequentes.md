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

O valor de `TESSERACT_BRIDGE_ADMIN_TOKEN` no arquivo `.env`
ou no ambiente do processo. Gere com
`python -c "import secrets; print(secrets.token_urlsafe(32))"`.
Reinicie após alterar o token. O token é uma credencial da API
administrativa, **não** a senha do banco SQLite.

## O botão Desbloquear não funciona

Cheque se a variável existe, tem pelo menos 16 caracteres e foi
carregada pelo processo. Token incorreto retorna **401**;
variável ausente retorna **503**. Não publique seu token em prints
ou logs. Verifique o console do navegador para erros de rede.
O token é mantido somente na memória da página após desbloqueio.

## Para que serve o arquivo .env?

Define infraestrutura, não receitas, GPIO ou PID:

```dotenv
TESSERACT_BRIDGE_DB=./data/private/imported.sqlite3
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

O `TESSERACT_BRIDGE_DB` aponta para um arquivo ainda não criado.
A importação só gera o SQLite na execução **sem** `--dry-run`.
Para instalação vazia use `bridge.sqlite3` e execute
`python -m storage.cli init`. Não substitua uma instalação importada
por um banco vazio por engano.

## O importador rejeita pump_b1 com remote_control

Se `remote_control: true` não possui `state_topic`, o schema
recusa o cadastro. Corrija o tópico real na cópia de origem ou use
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
