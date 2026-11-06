# 15 — Assistente de instalação

Referência atual: **2.0.0-setup.12**, branch `feature/sqlite-full-migration`.
O [manual consolidado](20-instalacao-migracao-2.0.0.md) cobre o fluxo completo;
este guia descreve abertura, retomada e cancelamento.

## Iniciar sem configuração anterior

Após clonar a branch e instalar `requirements.txt` na venv, execute na raiz:

```powershell
python -m setup
```

Não copie `.env.example` nem crie SQLite antes de abrir o assistente.
Acesse `http://127.0.0.1:8090` ou `http://localhost:8090`, conforme a URL impressa.
Se a porta estiver ocupada, use `python -m setup --port 8091` e a porta correspondente
no navegador. Reinicie o processo depois de atualizar o código e recarregue a página.

O assistente tem cinco telas: idioma/aparência, dados, infraestrutura, credencial
e conclusão. Pode criar ORM vazio ou importar dados antigos em staging, revisar
pendências, preparar configuração e publicar a instalação com confirmação.
Abrir o setup não inicializa DeviceRuntime, GPIO, painel operacional ou MQTT.

## Acesso ao Raspberry

O servidor escuta somente em loopback, sem debugger/reloader. No computador cliente:

```bash
ssh -N -L 8090:127.0.0.1:8090 usuario@raspberry
```

Abra a URL local no computador; mantenha a mesma porta nas duas pontas do túnel.
Formulários exigem sessão/CSRF e origem local correspondente. Não exponha o
instalador por proxy público. Caminhos digitados pertencem ao servidor; arquivos
no computador cliente devem ser enviados por upload.

## Retomar e cancelar

Ctrl+C encerra o servidor e preserva a tentativa. Execute novamente para retomar.
A sessão HTTP é nova: recarregue a página antes de enviar formulários.
Somente um processo pode manter o lock da instalação.

Antes de publicar, Cancelar remove somente o staging identificado pela tentativa.
Arquivos da instalação antiga permanecem intactos. Manifesto e lock ficam em
`data/private/setup/`; não os edite manualmente. Estado desconhecido/corrompido
impede continuar e fica preservado para diagnóstico.

Depois de iniciada a publicação, use as ações de recuperação da tela Concluir.
Cancelar não remove uma instalação publicada. Consulte [recuperação e serviço](19-conclusao-servico.md).

## Modo de operação

Instalação vazia não recebe dispositivos ou receitas fictícias e é publicada em
simulação. O Bridge abre a configuração administrativa sem criar runtime físico;
o monitor serial fica disponível para diagnóstico explícito, mesmo sem cadastro.

A autorização ORM para modo configurado depende da conclusão válida e explícita
do setup. Pendências e publicação interrompida mantêm o bloqueio físico. Não há
uma etapa adicional obrigatória de homologação ORM após concluir; isso não remove
intertravamentos nem constitui homologação física do equipamento.

## Diagnóstico e validação

```powershell
python -m setup.doctor
python -m pytest tests/test_setup.py -q
```

O diagnóstico não abre o banco ou o `.env` para revelar conteúdo e não repara
arquivos. O núcleo genérico de configuração/persistência/layout fica em
`reusable/guided_setup/`; veja o [guia de reaproveitamento](../modules/guided-setup/README.md).

### Revisão da importação — setup.13

No modo SQLite, informe o arquivo ou selecione uma pasta. A descoberta procura
`.sqlite3`, `.sqlite` e `.db` na pasta e em `data/`, `data/public/` e `data/private/`,
sem busca recursiva irrestrita. Selecione apenas um banco por importação. Bancos
não importáveis aparecem desabilitados; pare a instalação antiga e forneça um
backup consistente, sem arquivos WAL/SHM/journal pendentes.

A importação parcial não ignora uma configuração de dispositivos inválida. O
relatório diferencia lista vazia, campos obrigatórios ausentes, YAML inválido e
controle remoto sem tópico de estado, sem mostrar valores ou credenciais. Para
configuração vazia, use o fluxo de instalação sem dados. Outras falhas de esquema
ainda exigem revisar uma cópia do arquivo; não habilite hardware para contorná-las.

Se o descarte falhar, o diagnóstico distingue publicação existente de arquivos
bloqueados. No primeiro caso use recuperação/rollback; no segundo feche o programa
que usa os temporários e repita. A tentativa permanece disponível para repetição.

### Escolha de controle remoto na migração (setup.15)

Quando um atuador legado solicita `hardware.remote_control: true` sem informar
`state_topic`, a importação apresenta os dispositivos afetados em um popup.
Nenhuma opção é escolhida automaticamente:

- **Manter remoto:** informe o tópico real de estado de cada dispositivo listado.
  O setup valida o formato, mas não testa MQTT nem garante que o equipamento
  publique nesse tópico. Não há geração automática de tópicos.
- **Desativar nos afetados:** aplica `remote_control: false` somente nos itens
  listados. Os demais dispositivos conservam a configuração original. O acesso
  local continua sujeito às regras normais; a autorização de acionamento remoto
  pelo Tesseract/MashControl é retirada nesses itens.

Fechar o popup permite revisar a seleção; o botão **Revisar controle remoto** o
abre novamente. A decisão reaplica a importação usando os arquivos selecionados,
mantém a escolha de importação parcial e registra os ajustes no relatório e no
histórico de migração. O original nunca é regravado. Escolher manter remoto não
inicia hardware, não autoriza runtime e não altera os intertravamentos de gás.

Selecione a raiz da instalação antiga (a pasta que contém `data/`). Quando o
material recebido for apenas a pasta `data`, coloque-a numa pasta de origem e
selecione essa pasta superior.

### Descartar temporários no Windows (setup.16)

O descarte remove somente a pasta da tentativa atual e volta ao início. Arquivos
somente leitura são liberados para exclusão dentro dessa pasta. O lock do próprio
setup fica fora dela e não deve ser apagado manualmente enquanto o setup roda.

Se a resposta for `abort_files_busy`, a tela informa o caminho relativo do arquivo
bloqueado, quando disponível, e o código do sistema. Feche o visualizador de banco,
editor ou outro programa que o esteja usando e repita o descarte. A tentativa
permanece registrada até a exclusão terminar; alguns temporários já podem ter
sido removidos. A operação pode ser repetida.

Se a resposta for `abort_publication_exists`, existe uma publicação no destino.
Abra **Concluir instalação** para examinar o estado e usar a recuperação ou o
rollback permitido. O descarte de temporários não remove o banco publicado nem
ignora essa proteção. O status HTTP 409 sozinho não identifica qual caso ocorreu.

### Relatório restrito ao escopo de importação (setup.17)

Arquivos de código, documentação, `.gitkeep` e exemplos não aparecem como itens
ignorados no relatório visível. Arquivos reconhecidos pela migração que o usuário
não selecionou continuam identificados, assim como avisos e erros de arquivos
importáveis. O filtro também vale para relatórios salvos por builds anteriores.
O inventário técnico de descoberta permanece disponível para diagnóstico.

### Logs de diagnóstico (setup.18)

O setup grava `data/private/setup/logs/setup.jsonl`, fora da pasta da tentativa.
O log permanece depois de cancelar a tentativa e descartar temporários. O terminal
mostra esse caminho ao iniciar. Há rotação automática de até três arquivos de
1 MiB cada: `setup.jsonl`, `setup.jsonl.1` e `setup.jsonl.2`.

Use **Baixar log de diagnóstico**, disponível nas telas do assistente. O arquivo
baixado reúne as partes ainda retidas, da mais antiga para a mais recente. O
endpoint segue a mesma restrição local do setup e não permite escolher caminhos.

Em caso de falha, informe o **ID do diagnóstico** mostrado na tela e envie o log.
Repita a operação após atualizar: erros de builds antigos não podem ser
reconstruídos retroativamente. O arquivo registra build, data/hora UTC, tentativa,
etapa, tipo da exceção, códigos `errno`/`winerror`/SQLite quando disponíveis e
arquivo/função/linha do código. Na captura de dados, também registra o nome relativo
do arquivo importável. O comprimento do caminho envolvido ajuda a identificar
limites de caminho no Windows, sem registrar seu caminho absoluto.

O log não grava corpos HTTP, cookies, CSRF, tokens, tópicos fornecidos pelo usuário,
conteúdo YAML/JSON, mensagens brutas de exceção, linhas de código ou variáveis
locais. Se o disco ou a permissão também impedirem salvar o log, o erro original
continua prevalecendo; o download informa a indisponibilidade.

### Caminhos longos no Windows (setup.19)

O log de uma falha real registrou `FileNotFoundError`, `errno=2`, na criação da
cópia temporária de `data/control_defaults.json`, com destino de 268 caracteres.
Essa falha ocorre antes da validação YAML/JSON e é compatível com o limite
tradicional de caminhos do Windows.

Novas tentativas usam nomes compactos de pastas, sem truncar o identificador
UUID. As cópias de importação e SQLite também usam nomes internos mais curtos.
O setup verifica previamente espaço no comprimento do caminho para os arquivos
mais profundos e journals SQLite. Não altera o registro do Windows.

Após atualizar um clone que já apresentou essa falha:

1. Encerre e reinicie o setup atualizado.
2. Cancele a tentativa antiga e descarte os temporários.
3. Inicie uma nova tentativa e repita a descoberta/importação.

A tentativa antiga mantém o layout anterior até ser descartada; candidatos já
preparados não são movidos silenciosamente. Se mesmo a nova tentativa exceder o
limite, use uma pasta curta para o clone, por exemplo `C:\TesseractBridge`.
Os dados de origem e o banco publicado não são alterados por essa correção.
