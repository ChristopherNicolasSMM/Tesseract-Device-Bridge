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
| Revisão relacional `bridge_orm_0002` | Implementada, aguardando homologação local | Calibração, receita ativa, sessão, alarmes e snapshot térmico equivalentes |
| Histórico de revisões e auditoria | Pendente | Modelos tipados, importação imutável e conferência |
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

## Homologar a nova cópia no Windows

Com o Bridge experimental parado e o `.env` apontando para
`imported.sqlite3`:

```powershell
git pull --ff-only origin feature/sqlite-full-migration
python -m pip install -r requirements.txt
python -m pytest -q tests/test_orm_operational.py tests/test_orm_normalize.py tests/test_orm_repository.py
python -m storage.cli normalize --dry-run
python -m storage.cli normalize --output ./data/private/normalized-v2.sqlite3
python -m storage.cli orm-audit --candidate ./data/private/normalized-v2.sqlite3
python -m storage.cli status
```

O `normalized-candidate.sqlite3` anterior continua válido para a
**primeira etapa**, mas está na revisão `bridge_orm_0001`.
Não deve ser sobrescrito nem usado para a auditoria 0002.
O `normalized-v2.sqlite3` deve ser um **novo arquivo inexistente**.

A auditoria 0002 deve retornar `result=OK`,
`alembic=bridge_orm_0002` e `runtime_cutover_enabled=false`.

**Não** edite `TESSERACT_BRIDGE_DB` para apontar à cópia experimental.
O runtime continua ativo no banco `imported.sqlite3`, em simulação.
Somente após repositórios, transações, segurança e testes completos
devemos realizar o cutover para ORM.
