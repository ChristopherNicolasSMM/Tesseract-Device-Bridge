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
validadores de pasta. Adaptador HTTP/multipart, grid, modal e indicador de processamento são
implementados em setup.browser_import e setup/static/setup.js. Não há endpoint de leitura arbitrária de caminhos.

## Segurança e limites

Origens apenas leitura, captura privada, limites existentes de quantidade/tamanho,
recusa de symlinks, SQLite sem sidecars e rollback por descarte do staging mantidos.
A captura de arquivos não é snapshot transacional entre vários arquivos; pare a
instalação antiga antes de importar. O motor não conclui nem publica instalação.
O protocolo de publicação/recuperação final e o estado operacional pertencem às
serviços setup.infrastructure, security, publication e finalize. Permissões do SO e teste real de interrupção continuam na homologação.

## Validação local

python -m pytest tests/test_setup_partial.py tests/test_setup_legacy.py tests/test_setup_sqlite_import.py tests/test_setup_bootstrap.py -q
python -m pytest -q

### Diagnóstico por etapa e isolamento (setup.14)

A origem digitada e o tipo de descoberta ficam no manifesto privado do setup,
separados do caminho da cópia capturada. A página repõe esses valores após o
redirecionamento e em recargas; os caminhos nunca são colocados no cookie.

O preflight YAML/JSON valida os padrões e configurações de controle da própria
origem, passando `defaults` explicitamente. Não consulta `factory_settings()` nem
o banco operacional selecionado no ambiente, que pode ainda não estar disponível.

Falhas retornam códigos estáveis de preparação (`import_preparation_failed`),
gravação intermediária (`legacy_write_failed`) ou conversão/verificação ORM
(`orm_conversion_failed`), acompanhados de uma categoria estática da causa.
Mensagens brutas de exceção, SQL, valores importados e credenciais não são exibidos
nem persistidos. Avisos da coleta parcial são preservados mesmo se a etapa seguinte
falhar. Um relatório de falha sempre tem `database=null` e não autoriza runtime.

A referência versionada em `tests/fixtures/legacy_main/` reproduz os quatro arquivos
públicos consultados da `main` em 06/11/2026: seis dispositivos e receita base.
Os testes cobrem importação estrita/parcial sem banco operacional acessível.
Os arquivos privados de uma instalação real continuam exigindo validação própria;
a referência não comprova equivalência a uma origem com sete dispositivos.

### Resolução explícita do remoto legado

`remote_state_topics` é um mapeamento opcional de ID para tópico real fornecido
pelo usuário. `_normalize_legacy_config` aceita apenas IDs classificados por
`_needs_remote_disable`, valida os tópicos, trabalha em `deepcopy` e registra cada
mudança em `repairs`. Essa opção é mutuamente exclusiva com
`disable_invalid_remote_control`. A validação completa de `BridgeConfig` ocorre
após aplicar a decisão; configurações de aquecimento não são relaxadas.

O adaptador web usa `remote_policy=keep|disable_invalid` e campos
`state_topic:<id>`, com o mesmo CSRF e limite de corpo do restante do setup. O
relatório bloqueante contém `remote_conflicts` para renderização escapada no
popup; seleção e modo parcial ficam no manifesto privado. O popup não serve como
validação de segurança: POSTs diretos passam pelas mesmas regras do backend.
