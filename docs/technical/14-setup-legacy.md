# 14 — Descoberta e importação YAML/JSON

O motor e a CLI operam somente em staging e são compartilhados pelo adaptador
HTTP do assistente. A importação não altera runtime, .env ativo ou banco definitivo.
Validação e pendências: [matriz de homologação](../homologacao/setup-2.0.0.md).

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
válida e referências completas; importação parcial é opcional com --allow-partial; veja o
[contrato consolidado](16-setup-import-contract.md).

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

## Integração atual

O motor também é usado pelo assistente visual. Importação SQLite e relatórios
estruturados estão disponíveis; [contrato](16-setup-import-contract.md) e
[importação no navegador](../manual/16-importacao-navegador.md).
Somente a publicação explícita transforma um candidato em instalação definitiva.
