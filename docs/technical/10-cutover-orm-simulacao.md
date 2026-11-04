# 10 — Cutover ORM experimental (somente simulação) | 2.0.0

> **Estado:** implementação em homologação, **não** autorizada para
> Raspberry Pi físico ou cargas GLP. A `main` e `imported.sqlite3`
> permanecem preservadas. O modo padrão continua sendo `legacy`.

## Arquitetura e contratos

A v2.0.0 agora contém dois backends de persistência:

- `legacy` (padrão): camada original `storage/sqlite_store.py`,
  que continua compatível e independente.
- `orm` (experimental): `storage/store_router.py` delega a
  `storage/repositories/write.py` e aos models SQLAlchemy.
  Dados operacionais, receitas, administração, logs de auditoria e
  sessões são gravados apenas nas tabelas relacionais da revisão 0003.

Ambos utilizam interfaces compatíveis para o painel e motor de receitas,
mas **não há escrita dupla**. No modo ORM, a API de SQL direto da
camada anterior fica bloqueada. O carregamento da configuração mantém
um snapshot imutável no runtime até reinicialização supervisionada.

Regras de compatibilidade entre configuração, receitas e calibrações
foram centralizadas em `tesseract_bridge/services/validation.py`,
compartilhadas por administração e repositórios.

A conexão transacional inicia com `BEGIN IMMEDIATE` para serializar
operações de leitura + verificação de revisão + escrita sob SQLite.
Históricos de configurações, rascunhos, receitas e auditoria são
persistidos como registros relacionais na mesma transação.
Atualizações de receitas preservam a chave da receita ativa e
históricos anteriores.

## Portão de segurança

O processo recusa `STORAGE_MODE=orm` se:

1. `TESSERACT_BRIDGE_SIMULATION_ONLY` não estiver ativado;
2. `TESSERACT_BRIDGE_DB` não tiver sido definido explicitamente;
3. O arquivo não existir, não tiver modelos ORM ou não estiver na
   versão Alembic `bridge_orm_0003`.

O modo de simulação força MQTT desabilitado, backend simulado e
`127.0.0.1` na porta de teste. Qualquer tentativa de operação ORM
real gera erro em vez de reverter silenciosamente ao SQL legado.

**Atenção:** esta proteção não substitui homologação de GPIO,
intertravamentos, bombas, resistências, corte de chama, watchdog,
recuperação ou controle de acesso. Não exponha o painel à Internet.

## Procedimento de teste isolado no Windows

Pare o processo do Bridge. Na branch de migração:

```powershell
git pull --ff-only origin feature/sqlite-full-migration
python -m pip install -r requirements.txt
python -m pytest -q tests/test_orm_cutover.py tests/test_orm_history.py tests/test_orm_operational.py tests/test_orm_repository.py tests/test_orm_normalize.py
```

**Primeiro confirme a cópia da revisão 0003** sem alterações
na origem. Com `.env` ainda apontando para `imported.sqlite3`:

```powershell
python -m storage.cli orm-audit --candidate ./data/private/normalized-v3.sqlite3
```

O retorno precisa indicar `result=OK`,
`alembic=bridge_orm_0003` e contagens coerentes. Se a cópia ainda
não existir, crie-a com `normalize --output` em um nome novo
antes de executar auditoria.

**Crie uma cópia de trabalho para o cutover**, preservando também
a `normalized-v3.sqlite3` que passou na auditoria:

```powershell
Test-Path .\data\private\orm-sandbox.sqlite3
# Se False, e com o Bridge parado:
Copy-Item .\data\private\normalized-v3.sqlite3 .\data\private\orm-sandbox.sqlite3
```

O `Copy-Item` somente deve ser executado se o destino não existir.
Não sobrescreva cópias anteriores.

**Selecione o modo ORM somente no processo do PowerShell atual**:

```powershell
$env:TESSERACT_BRIDGE_DB="./data/private/orm-sandbox.sqlite3"
$env:TESSERACT_BRIDGE_STORAGE_MODE="orm"
$env:TESSERACT_BRIDGE_SIMULATION_ONLY="1"
$env:TESSERACT_BRIDGE_TEST_PANEL_PORT="8089"

python -m storage.cli status
python run_bridge.py
```

O status precisa indicar `storage_mode=orm`,
`backend_runtime=simulated`, `mqtt_runtime_enabled=false`.
Teste navegação no painel, cadastro e atualização de receita,
Configurações, Calibração, criação/aprovação de rascunho e backup.
Aprovar um hardware editado não aplica seus pinos na sessão atual.

**As alterações feitas na cópia `orm-sandbox.sqlite3` são reais nessa cópia, não
são refletidas no banco legado**. Uma auditoria comparativa com a
origem, depois de editar dados do ORM, deve indicar divergência:
isso é esperado e impede tratar os dois esquemas como sincronizados.

## Voltar ao modo anterior

Pare o painel com `Ctrl+C` e restaure as variáveis originais:

```powershell
Remove-Item Env:TESSERACT_BRIDGE_STORAGE_MODE
Remove-Item Env:TESSERACT_BRIDGE_DB
Remove-Item Env:TESSERACT_BRIDGE_SIMULATION_ONLY
Remove-Item Env:TESSERACT_BRIDGE_TEST_PANEL_PORT
```

O novo processo carregará novamente o `.env` original.
Confirme `python -m storage.cli status` e
`storage_mode=legacy`, com banco `imported.sqlite3`.

Nenhuma sincronização reversa entre a cópia experimental e
`imported.sqlite3` está disponível; exporte mudanças úteis
separadamente e aplique-as pelos meios regulares após validação.

## Critérios de aceite pendentes

- A bateria completa no Windows e CI Python 3.9 deve passar, incluindo
  concorrência e cenários de falha do SQLite.
- Testes funcionais de todos os endpoints administrativos, diagnósticos e receitas,
  inclusive estados de erro e calibração.
- Repetir os testes em Raspberry Pi em **modo simulado**, e somente
  depois planejar fase de GPIO real e intertravamentos.
- Consolidar migração de produção, backup, rollback e separação
  definitiva das tabelas legadas.
- O backend real do ORM permanecerá bloqueado até autorização
  explícita após homologação, não por simples alteração no `.env`.

Leia também [Estado de cutover](09-status-cutover-v2.md) e
[Normalização relacional](08-normalizacao-sqlalchemy.md).
