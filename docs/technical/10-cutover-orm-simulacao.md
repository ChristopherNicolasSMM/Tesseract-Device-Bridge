# 10 — Sandbox ORM e histórico do cutover | 2.0.0

Este procedimento avançado preserva a validação em cópias isoladas anterior
ao instalador. Para instalações atuais, use o [manual de setup](../manual/20-instalacao-migracao-2.0.0.md).
A homologação física permanece pendente; o bloqueio do código termina após
setup válido e autorização explícita do modo configurado.

## 0. Como saber qual banco está ativo

Execute `python -m storage.cli status` **antes** de qualquer auditoria.
Se mostrar `storage_mode=orm` e `db=...normalized-v3.sqlite3`,
essa cópia está selecionada para execução e pode ter sido alterada.
**Não a use como nova fonte da auditoria e não a sobrescreva.**

Para verificar uma migração a partir da origem legada, com o
Bridge desligado, estabeleça a origem explicitamente apenas na
sessão PowerShell atual:

```powershell
$env:TESSERACT_BRIDGE_STORAGE_MODE="legacy"
$env:TESSERACT_BRIDGE_DB="./data/private/imported.sqlite3"
python -m storage.cli status
```

Só depois gere um **novo destino inexistente** com
`python -m storage.cli normalize --output <nome-novo>.sqlite3`
e use `orm-audit --candidate <nome-novo>.sqlite3`.
Mantenha `normalized-v3.sqlite3`, `orm-sandbox.sqlite3` e
`imported.sqlite3` intactos. Para retomar o ORM, configure
`STORAGE_MODE=orm`, `SIMULATION_ONLY=1` e o caminho da
**cópia de trabalho**, não da cópia de auditoria.

## Referências cruzadas na validação de controle térmico

A validação de parâmetros utiliza os padrões de fábrica do
**mesmo banco relacional** acessado pelo repositório.
Assim, testes que constroem uma cópia ORM isolada não consultam
a configuração global `.env` para encontrar `control_factory`.
O sandbox deste roteiro usa simulação e não existe escrita dupla.

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

## Portão de segurança atual

O runtime verifica caminho explícito, esquema ORM compatível e revisão Alembic.
Instalações publicadas também exigem recibo consistente e identidade entre
`.env` e banco. Publicação interrompida ou dados pendentes impedem operação
física. O setup concluído pode autorizar o modo operacional; não existe um
bloqueio ORM permanente adicional até outra entrega.

Os sandboxes não publicados deste roteiro devem continuar em simulação.
A simulação força backend simulado, MQTT desligado e painel em loopback.
Intertravamentos e validações de hardware permanecem ativos.

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

**Importante:** a auditoria de equivalência só é válida para uma
cópia recém-criada e ainda não utilizada para operar o Bridge.
O estado da sessão em `imported.sqlite3` é mutável e seu timestamp
é atualizado quando o runtime salva a sessão. Se ele mudar após a
normalização, `orm-audit` rejeitará corretamente a comparação.
Não use `--candidate` apontando para um banco `orm-sandbox.sqlite3`
que já foi editado pelo runtime.

Se ocorrer `Timestamp do estado de sessão divergente`:

1. Pare o Bridge e feche os processos que gravam nos bancos.
2. Confirme `storage_mode=legacy` e `db=...imported.sqlite3`
   com `python -m storage.cli status`.
3. Gere outra cópia, com nome ainda inexistente:
   `python -m storage.cli normalize --output ./data/private/normalized-v3-recheck.sqlite3`.
4. Audite **imediatamente**:
   `python -m storage.cli orm-audit --candidate ./data/private/normalized-v3-recheck.sqlite3`.
5. Preserve `normalized-v3.sqlite3` e os snapshots anteriores;
   não sobrescreva nenhum arquivo validado.

Esta é uma nova comparação pontual de dados mutáveis, e não
uma migração Alembic adicional. Não é necessário alterar models,
timestamps ou permissões do SQLite para que a auditoria passe.

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
- A operação física exige setup válido e autorização explícita; editar apenas
  o `.env` não substitui a publicação consistente.

Leia também [Estado de cutover](09-status-cutover-v2.md) e
[Normalização relacional](08-normalizacao-sqlalchemy.md).
