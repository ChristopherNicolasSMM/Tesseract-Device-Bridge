# Análise de arquivos possivelmente sem uso

Data: 05/11/2026. Branch: `feature/sqlite-full-migration`.
Base examinada: `af3f75e9e49190303b7f4843c46626d184816c4f`.
Escopo: análise estática de arquivos versionados e referências internas.
Nenhum arquivo de aplicação foi removido ou alterado; testes não foram executados.

## Resultado

Há **3 JavaScripts candidatos à remoção**, **4 SVGs candidatos a arquivamento ou
ligação explícita à documentação** e **1 script manual a revisar**. Não foi
identificado módulo Python de aplicação claramente órfão pelos imports estáticos.
Ausência de referência interna não prova ausência de consumidor externo.

Foram examinados 273 arquivos versionados: 53 de documentação, 63 de testes
(60 Python + 3 fixtures JSON) e 157 dos demais componentes/configuração.
No total, 167 arquivos Python foram analisados, incluindo testes e __init__.py.
Essas contagens são da base indicada, antes da inclusão deste relatório.

## 1. Candidatos mais fortes: JavaScripts não carregados

| Arquivo | Bytes | Evidência | Recomendação |
|---|---:|---|---|
| panel/templates/funcoes.js | 59.768 | Nenhuma referência externa ao próprio arquivo nos versionados; 79 funções nomeadas também presentes em index.html | Candidato à remoção após comparar comportamento e conferir UI |
| panel/templates/funcoes_bkp_old.js | 63.898 | Nenhuma referência externa; nome de backup e 78 funções nomeadas também presentes em index.html | Prioridade de limpeza, preservando histórico Git |
| panel/templates/newfuncoes.js | 67.859 | Nenhuma referência externa; 57 funções nomeadas também presentes em index.html | Comparar alterações de protótipo antes de descartar |

Total: **191.525 bytes, aproximadamente 187 KiB** no checkout.

O painel renderiza index.html em `panel/app.py`. O template contém JavaScript
inline e carrega `/static/control-settings.js`, `/static/serial-monitor.js` e
`/static/admin-sqlite.js`. Os três candidatos não são incluídos por Jinja, tags
script, rotas de envio de arquivo, testes, documentação ou scripts versionados.
Eles estão em templates/, não no diretório static/ servido pela rota padrão.

A comparação de nomes foi feita por expressão regular sobre declarações
`function nome(...)`; **não é comparação semântica**. Os conteúdos não são cópias
byte a byte e podem preservar mudanças antigas não incorporadas ao painel ativo.
Não substituir o JS inline por qualquer um deles sem revisar diferenças.

## 2. Recursos gráficos órfãos na documentação

| Arquivo em docs/technical/svg/ | Bytes | Situação |
|---|---:|---|
| componente-realgpiobackend.svg | 28.908 | Sem referência por nome nos arquivos versionados |
| componente-recipeengine.svg | 30.463 | Sem referência por nome nos arquivos versionados |
| container-tesseract-device-bridge-dentro-do-raspberry-pi.svg | 38.846 | Sem referência por nome nos arquivos versionados |
| contexto-tesseract-device-bridge.svg | 31.356 | Sem referência por nome nos arquivos versionados |

Total: **129.573 bytes, aproximadamente 127 KiB**. Os guias técnicos possuem
diagramas Mermaid; não foi encontrada ligação a esses SVGs. Eles não participam
do runtime, mas podem ser exportações históricas ou ter links externos.

Preferência: comparar o conteúdo com a arquitetura atual e então ligá-los a um
índice histórico, ou remover do checkout mantendo o histórico Git. Não tratá-los
como erro funcional nem presumir que são renderizações atuais dos diagramas.

JavaScripts + SVGs somam 321.098 bytes (aproximadamente 314 KiB). Isso é espaço
no checkout; uma exclusão normal não elimina os objetos do histórico Git.

## 3. Ferramenta fora do fluxo automático

`tools/ajuste_fontes_linux` (109 bytes) contém comandos de fontes/cache e um
comando de instalação de Tailscale por script remoto. Não há invocação pelos
instaladores, systemd, setup ou CI. Há uma referência descritiva na auditoria
inicial, não uma execução.

Classificação: **receita manual**, não dependência operacional. Recomenda-se
transferir o procedimento, se ainda necessário, para documentação específica de
ambiente; separar fontes de instalação de VPN. Pode haver uso manual externo.
Seu conteúdo não foi executado nesta análise.

## 4. Arquivos que parecem sem uso, mas devem permanecer

| Grupo | Evidência de uso/contrato |
|---|---|
| run_bridge.py / run_panel.py | Entrypoints CLI e serviço, não precisam ser importados por outro módulo |
| setup/__main__.py, doctor.py, import_legacy.py | Comandos `python -m setup`, `setup.doctor` e `setup.import_legacy` |
| storage/cli.py | CLI de status/compatibilidade/normalização |
| storage/alembic/env.py e versions/bridge_orm_0001..0003.py | Carregamento por Alembic; script_location em alembic.ini e bootstrap |
| tools/gpio_test.py | Diagnóstico manual explícito, fora do setup e com potencial de acionar hardware |
| tools/migrate_legacy_to_sqlite.py | Compatibilidade de migração manual; não substitui o setup |
| storage/sqlite_store.py e migrations/*.sql | Compatibilidade, importadores e bootstrap/perfis compartilhados; não excluir por o ORM ser atual |
| data/public/devices.yml.example | EXAMPLE_CONFIG_PATH, documentação e teste de validade do exemplo |
| data/public/devices.heating-source.yml.example | Exemplo documentado de fontes térmicas, não cadastro operacional |
| data/public/receita.json | Catálogo vazio de referência legado; caminho reconhecido pelo importador, sem seed operacional |
| data/control_defaults.json | Entrada reconhecida pelo importador de padrões; runtime atual usa perfis persistidos/constantes de bootstrap |
| tests/fixtures/*.json | Contratos MQTT consumidos pelos testes de telemetria/controle |
| setup/static/setup.css | Arquivo de overrides hoje só com comentário, mas URL referenciada pelo template e testes |
| shared_ui/__init__.py | Adaptador ativo de /shared-ui/theme.css; fonte CSS fica em reusable/guided_setup/static |
| reusable/** | Importado pelo setup/serial/shared_ui e distribuível separadamente; copiar só setup/ é insuficiente |
| __init__.py e .gitkeep | Estrutura de pacotes/diretórios, mesmo quando vazios |
| .env.example, .python-version, pyproject.toml, reusable/pyproject.toml, workflow CI | Configuração consumida por ferramentas, operadores ou empacotamento |

O arquivo `data/public/receita.json` está vazio (`[]`) e não fornece receitas à
instalação ORM limpa. Isso não torna todos os caminhos de receita JSON obsoletos:
continuam sendo parte do contrato de importação das instalações anteriores.

## 5. Artefato local não versionado

Foi encontrado `setup-etapa-2.patch` no workspace desta análise, com 40.328 bytes.
Ele é ignorado pelo padrão `*.patch` e não consta em git ls-files. É um artefato
local de entrega antiga, não um arquivo distribuído no clone atual. Não deve ser
confundido com pendência de limpeza do repositório nem reaplicado sobre entregas
posteriores. A análise não modifica nem elimina esse arquivo.

## 6. Método e limites

1. Inventário com git ls-files, separando versão distribuída de artefato local.
2. AST dos módulos Python: imports absolutos/relativos e consumidores em produção
   ou testes. Os 12 arquivos sem imports de produção recebidos são entrypoints,
   CLIs, ferramentas manuais ou arquivos do Alembic, classificados acima.
3. Busca por nome de recursos em todos os arquivos versionados, incluindo scripts,
   testes, workflow e documentação; inspeção de render_template, includes e rotas.
4. Inspeção de carregamentos dinâmicos: Alembic, blueprints estáticos, templates
   reutilizáveis e seleção de backend GPIO por importlib.import_module.
5. Hash SHA-256 dos arquivos não vazios: nenhuma duplicata exata encontrada.
6. Comparação limitada de nomes de funções dos JS históricos com o HTML ativo.

Não foram executados testes, cobertura, navegador, scripts de serviço ou hardware.
O levantamento não mede frequência de uso, não determina funções/métodos mortos
e não comprova equivalência entre os JS. Não detecta usos por código externo,
links publicados fora do repositório ou comandos manuais de operadores.

## 7. Ordem recomendada para uma futura limpeza

1. Comparar os três JS com a implementação ativa e revisar as telas críticas
   (bombas, potência, receitas e alarmes) antes de removê-los em um commit isolado.
2. Decidir se os SVGs serão documentos históricos com links ou arquivos removidos.
3. Documentar/separar a receita manual de fontes/Tailscale.
4. Executar as regressões apropriadas e a validação visual após qualquer limpeza.
5. Preservar compatibilidade, migrações, exemplos, dados privados e entrypoints.

Não há recomendação de remover storage legacy, migrações Alembic, módulos
reutilizáveis ou arquivos operacionais privados nesta etapa.
