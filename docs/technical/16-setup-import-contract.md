# Etapa 4 — motor de importação consolidado

Entregas anteriores cobrem YAML/JSON e SQLite legado/ORM. Esta entrega completa
o contrato do motor com importação parcial explícita, eventos estruturados,
relatório seguro de falha e entrada de uploads em bytes. Testes escritos,
não executados pelo assistente por autorização do usuário.

## Importação parcial

CLI: acrescente --allow-partial somente para pasta YAML/JSON. Sem essa opção,
o comportamento continua estrito. Dados opcionais são validados em cópia privada,
por arquivo; listas receita.json também são validadas por entrada. Entradas
rejeitadas geram warning com caminho/index, sem conteúdo nem exception text.
Dados válidos permanecem, mas needs_review=true impede tratar a importação como
configuração aprovada. Dispositivos inválidos geram relatório needs_review
sem banco candidato. Não se cria hardware fictício nem se ignora bloqueio crítico.
SQLite corrompido ou incompatível continua rejeitado integralmente: não recuperar
linhas arbitrárias nem ocultar perda de integridade.

## Relatório

Eventos possuem categoria imported, warning, blocking_error ou ignored e código
estável, traduzível pela interface. Falhas gravam relatório privado sanitizado
em failed-*/report.json e propagam a exceção ao chamador. Logs não contêm segredos
do arquivo nem mensagem arbitrária de exceção. Relatórios de sucesso são gravados
com fsync/replace. O banco candidato é relativo ao staging; runtime_authorized
é sempre false. Repetir gera job independente e não sobrescreve importação anterior.

## Upload

setup.uploads recebe mapeamento explícito de caminhos legados reconhecidos para
bytes. Valida todos os nomes/tamanhos antes de gravar, bloqueia traversal, barra
invertida e caminhos desconhecidos, e mantém arquivos privados da tentativa.
Não extrai ZIP nem executa código. import_uploads usa os mesmos adaptadores e
validadores de pasta. Adaptador HTTP/multipart, grid, modal e progresso visual
entram na Etapa 6. Não há endpoint de leitura arbitrária de caminhos.

## Segurança e limites

Origens apenas leitura, captura privada, limites existentes de quantidade/tamanho,
recusa de symlinks, SQLite sem sidecars e rollback por descarte do staging mantidos.
A captura de arquivos não é snapshot transacional entre vários arquivos; pare a
instalação antiga antes de importar. O motor não conclui nem publica instalação.
O protocolo de publicação/recuperação final e o estado operacional pertencem às
Etapas 7–9. Permissões do SO e teste real de interrupção continuam na homologação.

## Validação local

python -m pytest tests/test_setup_partial.py tests/test_setup_legacy.py tests/test_setup_sqlite_import.py tests/test_setup_bootstrap.py -q
python -m pytest -q
