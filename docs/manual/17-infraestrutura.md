# Etapa 7 — Infraestrutura e preparação do .env

Atualize a branch feature e reinicie python -m setup.
O terminal e cabeçalho mostram 2.0.0-setup.7.
Após iniciar uma tentativa, abra Infraestrutura no menu ou conclua a revisão
da importação. Não é necessário preencher o caminho do banco manualmente.

## Campos

- SIMULATION_ONLY: padrão 1; força simulação, desativa MQTT e usa loopback.
  Valor 0 respeita o backend salvo no banco. Não altera o cadastro de hardware.
- TEST_PANEL_PORT: usada somente em simulação, padrão 8089.
- PANEL_HOST/PANEL_PORT: usados fora da simulação, padrões 127.0.0.1/8088.
  O formulário explica que ambos são ignorados quando a simulação está ativa.
- DB: gerado como ./data/private/bridge.sqlite3, relativo à raiz do clone novo.
  STORAGE_MODE é preparado como orm.

As portas aceitam inteiros 1–65535. Host aceita IP IPv4/IPv6 ou nome DNS, sem
protocolo, caminhos, aspas ou quebra de linha. Não se faz consulta DNS nem conexão
de saída. O teste de porta faz bind e fecha o socket, sem listen ou hardware.
Porta ocupada/reservada ou igual à do setup impede salvar. Para hostname ou IP não
local, a disponibilidade é marcada como não verificada, exigindo revisão no destino.
A disponibilidade é pontual e deverá ser reconferida antes de iniciar o serviço.

## Preparação segura

O .env lido é apenas o da instalação nova. A instalação antiga não é consultada.
Comentários e variáveis não editadas são preservados; linhas dos campos gerenciados
são atualizadas e duplicatas eliminadas. Conteúdo .env inválido ou symlink é recusado.
Valores secretos não são enviados ao navegador. Não executar scripts ou interpolar
comandos vindos do .env.

Cada salvamento grava um candidato UTF-8 privado e imutável em staging e só depois
atualiza o manifesto. Se o manifesto falhar, o candidato anterior continua selecionado.
Candidatos abandonados ficam para diagnóstico e são removidos ao cancelar a tentativa.
O manifesto registra o hash da origem .env para detectar alterações antes da futura
publicação; esse controle será consumido pela Etapa 9.

Esta etapa não publica o .env, não cria o banco definitivo e não libera GPIO.
A escolha por modo configurado será aplicada após conclusão válida do setup,
preservando intertravamentos existentes. Autenticação/admin token entram na Etapa 8.
A autorização do usuário continua sendo encerrar o bloqueio transitório ORM ao
concluir o setup, sem exigir outra fase posterior de homologação do ORM.

## Validação local — testes escritos, não executados pelo assistente

```powershell
git pull --ff-only origin feature/sqlite-full-migration
python -m pytest tests/test_setup_infrastructure.py tests/test_setup_i18n.py tests/test_setup_browser_import.py tests/test_setup.py -q
python -m pytest -q
python -m setup
```

Conferir campos e dicas nos dois idiomas, temas, porta ocupada, dados inválidos,
preservação do .env ativo, retomada e cancelamento. Não há db upgrade manual.
