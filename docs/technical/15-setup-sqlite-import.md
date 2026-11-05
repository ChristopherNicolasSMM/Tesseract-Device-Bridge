# Etapa 4 — entrega 2: importação direta SQLite

Publicação com testes escritos, não executados pelo assistente, conforme autorização.
Encerre o servidor setup para liberar o lock e use uma cópia limpa fora do clone novo:

```powershell
python -m setup.import_legacy --source "C:\\Backup\\bridge.sqlite3" --sqlite --import-data
python -m pytest tests/test_setup_sqlite_import.py tests/test_setup_legacy.py tests/test_setup_bootstrap.py -q
python -m pytest -q
```

A origem é lida como bytes, nunca aberta por SQLite, evitando recuperação ou
criação de arquivos auxiliares na instalação antiga. WAL/SHM/journal existentes
provocam recusa: pare o Bridge antigo e forneça backup consistente/checkpointado.
Não apague WAL manualmente. A captura tem limite de 256 MiB, hash e segunda
leitura para detectar alteração concorrente. Diretórios/arquivos symlink são recusados.

O esquema é identificado exclusivamente na cópia privada após quick_check e
foreign_key_check. SQLite desconhecido, corrompido ou revisão futura é recusado.
Legado usa normalização existente; ORM 0001/0002/0003 é copiado, atualizado via
Alembic e validado. Não se reaproveita o banco original como destino.
Cabeçalhos, configuração e receitas são reconstruídos; banco vazio fica needs_review.
Nenhum resultado autoriza runtime ou escreve .env/banco definitivo.

Cada importação cria diretório próprio, captura e relatório. Em falha os resíduos
ficam privados para diagnóstico; cancelar a tentativa remove apenas seu staging.
O relatório só é escrito após sucesso. Não há mesclagem automática com importações
anteriores nem seleção automática de candidato para publicação.

Continuidade: faltam tratamento parcial de entidades, progresso/log estruturado
de erros e preparação dos contratos de upload. A Etapa 4 ainda não está encerrada.
