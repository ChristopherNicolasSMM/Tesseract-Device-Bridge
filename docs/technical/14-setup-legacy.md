# Etapa 4 — entrega 1: descoberta e importação YAML/JSON

Esta entrega adiciona o motor e CLI local. Não altera rotas HTTP, runtime,
.env ou banco definitivo. Testes escritos e não executados pelo assistente,
conforme autorização do usuário; homologação local pendente.

## Uso

Encerre o servidor setup antes de importar (lock exclusivo).
Apenas inventariar, sem criar tentativa:

```powershell
python -m setup.import_legacy --source "C:\\Projetos\\Bridge-Antigo"
```

Importar os formatos reconhecidos em uma nova área privada de staging:

```powershell
python -m setup.import_legacy --source "C:\\Projetos\\Bridge-Antigo" --import-data
```

Use --select repetidamente para selecionar caminhos relativos. Havendo
devices.yml na raiz e em data/public, escolha exatamente um. Não há mesclagem
automática desses dois arquivos. O adaptador continua exigindo configuração
válida e referências completas; importação parcial ainda não é disponibilizada.

São listados arquivos apenas na raiz e nos diretórios conhecidos data,
data/public e data/private. Arquivos desconhecidos são ignorados. Symlinks são
recusados. Limites: 1000 entradas, 8 MiB por arquivo, 32 MiB por seleção.
Arquivos selecionados são copiados para staging e verificados por hash antes
de serem interpretados. YAML usa o parser seguro do importador existente.
Recomenda-se parar o Bridge antigo para obter um conjunto coerente entre arquivos.

A conversão reutiliza import_snapshot e normalize_copy: SQLite legado
intermediário apenas temporário, depois ORM normalizado. Não há escrita dupla
nem sincronização. Cada execução recebe diretório próprio; falhas conservam
temporários para diagnóstico, sem declarar importação concluída. Cancelar pelo
setup remove os temporários da tentativa, nunca os arquivos originais.
O relatório registra hashes, contagens, reparos, ignorados e banco candidato;
nenhum resultado autoriza runtime físico. O banco candidato não substitui o
banco vazio criado anteriormente.

## Validação local

```powershell
python -m pytest tests/test_setup_legacy.py tests/test_setup_bootstrap.py tests/test_storage_legacy_import.py tests/test_orm_normalize.py -q
python -m pytest -q
```

## Continuidade

Etapa 4 permanece em andamento: importação direta de SQLite legado/ORM,
revisões antigas, relatório estruturado de erros e importação parcial ainda
precisam de entrega. Upload e grid visual ficam na Etapa 6. Esta entrega não
afirma suporte a formatos não reconhecidos pelos adaptadores existentes.
