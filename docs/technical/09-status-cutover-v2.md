# 09 — Estado da migração e critérios de cutover | 2.0.0

> **Status de desenvolvimento em 2026-11-04:** a `main` continua
> estável e separada. O runtime da branch experimental ainda utiliza
> `sqlite_store.py`, com algumas tabelas legadas JSON.
> **Não está liberado para operação física.**

## Entregas e pendências

| Área | Situação | Critério de aceite |
|---|---|---|
| Importador YAML/JSON → SQLite | Concluído | Cópia original e backup intactos |
| Primeiro esquema SQLAlchemy/Alembic | Validado em Windows | 7 dispositivos, 2 receitas e 2 perfis |
| Revisão relacional `bridge_orm_0002` | **Validada pelo operador no Windows** | 7 dispositivos, 2 receitas, 2 perfis, 2 calibrações, receita ativa e sessão; auditoria OK |
| Histórico/revisões/rascunhos `bridge_orm_0003` | Implementada, aguardando testes e auditoria local | Tabelas de histórico, nós tipados e correspondência de payloads, IDs e timestamps |
| Serviços e repositórios ORM para toda escrita | Pendente | Transações, controle de revisão e testes de conflito |
| Troca do runtime para ORM | Pendente | Seleção de backend explícita, sem gravação dupla e com fallback seguro |
| Frontend administrativo v2 | Parcial | CRUD completo, autenticação/CSRF e tratamento seguro de erro |
| Remoção do esquema JSON legado | Pendente | Backup, migração conferida e rollback documentado |
| Testes integrados e CI Python 3.9 | Pendente | Suíte completa e homologação em Windows/Linux |
| Teste físico em Raspberry Pi | Pendente | GPIO isolado, GPIO real, sensores, GLP, emergência e recuperação |

## O que a revisão 0002 já cobre

A normalização foi ampliada para:
- `sensor_calibrations` → `bridge_sensor_calibrations_v2`;
- `active_recipe` → `bridge_active_recipe_v2`;
- `session_state.state_json` → `bridge_session_state_v2`,
  `bridge_session_fields_present_v2`, `bridge_session_alarms_v2`,
  `bridge_session_fired_hop_keys_v2`;
- snapshot de parâmetros térmicos da sessão → `bridge_control_profiles_v2`
  em chave separada, com pontos da curva e perfis normalizados.

O snapshot preserva explicitamente os campos ausentes em sessões legadas.
A comparação exige mesmo status, ID de alarmes, ordem, horários,
offsets, ROM IDs e parâmetro térmico por sessão.
Nenhuma dessas tabelas é lida pelo controle GPIO real nesta fase.

## Nova etapa: revisão 0003

A revisão Alembic **0003** modela os metadados de revisões e eventos em
tabelas próprias. Seus payloads históricos imutáveis são representados
por nós relacionais tipados, com relacionamento pai-filho, ordem de
listas e hash SHA-256 de conteúdo. Isso permite preservar versões antigas
sem continuar gravando documentos JSON nas novas tabelas.

A migração rejeita estruturas inválidas e compara todas as linhas do
histórico com a origem, inclusive eventos de auditoria e manifestos.
A fonte de dados operacionais **ainda é o SQLite legado** da branch:
as novas tabelas continuam em uma cópia de validação.

## Homologar a nova cópia no Windows

Com o Bridge experimental parado e o `.env` apontando para
`imported.sqlite3`:

```powershell
git pull --ff-only origin feature/sqlite-full-migration
python -m pip install -r requirements.txt
python -m pytest -q tests/test_orm_operational.py tests/test_orm_normalize.py tests/test_orm_repository.py tests/test_orm_history.py
python -m storage.cli normalize --dry-run
python -m storage.cli normalize --output ./data/private/normalized-v3.sqlite3
python -m storage.cli orm-audit --candidate ./data/private/normalized-v3.sqlite3
python -m storage.cli status
```

As cópias anteriores (`normalized-candidate.sqlite3` na 0001 e
`normalized-v2.sqlite3` na 0002) permanecem arquivadas.
A auditoria atual exige `normalized-v3.sqlite3` com a revisão
**0003**. Use um destino novo; jamais sobrescreva cópias validadas.

A auditoria 0003 deve retornar `result=OK`,
`alembic=bridge_orm_0003` e `runtime_cutover_enabled=false`.

**Não** edite `TESSERACT_BRIDGE_DB` para apontar à cópia experimental.
O runtime continua ativo no banco `imported.sqlite3`, em simulação.
Somente após repositórios, transações, segurança e testes completos
devemos realizar o cutover para ORM.
