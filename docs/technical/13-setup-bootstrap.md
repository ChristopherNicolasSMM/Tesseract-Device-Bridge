# Etapa 3 — Bootstrap ORM vazio

O botão de preparar banco vazio cria exclusivamente um SQLite no staging da
tentativa em andamento. Aplica Alembic até 0003, cria cabeçalhos simulados,
MQTT desativado e dois perfis de controle padrão. Dispositivos e receitas
permanecem vazios. Não escreve .env nem publica banco definitivo.

A validação operacional existente continua exigindo dispositivos. Esta etapa
não conclui o setup nem libera GPIO. Repetir valida o banco sem sobrescrever;
cancelar descarta o staging da tentativa.

Correção Windows: usar contextlib.closing tanto na validação SQLite quanto no
teste. O context manager nativo da conexão controla a transação, mas não fecha
o arquivo, causando WinError 32 ao cancelar a tentativa.

O erro Windows de fechamento foi identificado durante a entrega incremental.
Resultados atuais e pendências estão na [matriz de homologação](../homologacao/setup-2.0.0.md);
contagens antigas não certificam a versão atual. O candidato vazio pode ser
publicado pela tela Concluir, que mantém simulação e administração sem runtime.

Comandos:
```powershell
python -m pytest tests/test_setup_bootstrap.py -q
python -m pytest -q
python -m setup
```
