# Homologação da migração SQLite (branch feature/sqlite-full-migration)

**A main continua estável. Nunca execute os dois clones em modo GPIO real
ao mesmo tempo.** Inicialmente teste somente em simulação, com MQTT desativado.

## Instalação limpa

```bash
cd ~
git clone --branch feature/sqlite-full-migration --single-branch \
  https://github.com/ChristopherNicolasSMM/Tesseract-Device-Bridge.git \
  Tesseract-Device-Bridge-SQLite
cd Tesseract-Device-Bridge-SQLite
python3.9 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m storage.cli init
python -m storage.cli status
```

SQLite é a única fonte operacional. Banco em `data/private/bridge.sqlite3`,
ignorado pelo Git. Uma instalação vazia inicia com um sensor fictício em
`backend: simulated`, sem habilitar atuadores reais.

## Migrar cópia dos arquivos da instalação antiga

Interrompa qualquer brassagem e copie a pasta antiga para um diretório de
backup. **Não migre dados sendo escritos pelo processo.** O importador não
altera nem remove nada na origem. Se já criou o banco de teste acima, importe
para **outro nome**, sem sobrescrever um banco existente:

```bash
python tools/migrate_legacy_to_sqlite.py \
  --source ../Tesseract-Device-Bridge \
  --db ./data/private/imported.sqlite3 \
  --backup-dir ./backups --dry-run

python tools/migrate_legacy_to_sqlite.py \
  --source ../Tesseract-Device-Bridge \
  --db ./data/private/imported.sqlite3 \
  --backup-dir ./backups
```

Um ZIP privado é criado antes da importação. Ele pode conter senha MQTT e
cadastros privados. Nunca o inclua no repositório ou compartilhe sem proteção.


### Dispositivos legados com controle remoto incompleto

Se o `--dry-run` indicar `hardware.remote_control=true` sem `state_topic`
(como em `pump_b1`), o importador **recusa** a migração por padrão.
Não é erro do SQLite: o schema atual exige tópicos de estado/comando para
controle remoto explícito.

Para preservar o controle remoto, adicione o `state_topic` **real** na cópia
da configuração antiga e execute a validação novamente. Não invente um tópico
que não seja publicado pelo seu dispositivo.

Alternativamente, para importar com segurança sem editar o YAML antigo:

```powershell
python tools/migrate_legacy_to_sqlite.py --source ../Tesseract-Device-Bridge --db ./data/private/imported.sqlite3 --backup-dir ./backups --disable-invalid-remote-control --dry-run

python tools/migrate_legacy_to_sqlite.py --source ../Tesseract-Device-Bridge --db ./data/private/imported.sqlite3 --backup-dir ./backups --disable-invalid-remote-control
```

Essa opção é **explícita**, vale apenas para atuadores digitais/por janela
sem `state_topic` e sem `heating_source`, e importa esses dispositivos com
`remote_control=false`. O original permanece intacto. O backup conserva
os dados originais e o SQLite registra cada ajuste no manifesto/auditoria.
Não desabilita verificações de failsafe, ROM ID, GPIO nem proteção de gás.
Para reativar controle remoto, complete os dados pelo frontend, aprove
uma revisão e reinicie o processo de forma segura.

## Simulação isolada, mesmo com dados de GPIO real importados

```bash
export TESSERACT_BRIDGE_DB="$PWD/data/private/imported.sqlite3"
export TESSERACT_BRIDGE_SIMULATION_ONLY=1
export TESSERACT_BRIDGE_TEST_PANEL_PORT=8089
export TESSERACT_BRIDGE_ADMIN_TOKEN="substituir-por-segredo-aleatorio-com-32-caracteres"
python run_bridge.py
```

Abra `http://127.0.0.1:8089` na própria máquina. Esses overrides
desativam GPIO real e MQTT **somente nesta execução**, sem modificar o banco.

## Administração pelo frontend

Na aba Gerenciamento → Administração SQLite, informe o token do ambiente.
Cadastre dispositivos e conectividade, crie rascunhos, aprove revisões e
gere backup. O processo ativo não é alterado automaticamente.

Outras áreas permanecem nas abas existentes: Cadastro (receitas) e
Configurações (controle térmico, calibrações). Todas gravam em SQLite.

A autenticação do editor administrativo usa um token de ambiente. Antes do
uso definitivo em redes não confiáveis, implementar sessão autenticada,
proteção CSRF e HTTPS. **Não publique a interface diretamente na Internet.**

## Banco e segurança

- SQLite via `sqlite3` do Python 3.9, sem servidor adicional.
- Migrações SQL versionadas, transações, `foreign_keys=ON`,
  `synchronous=FULL`, journal DELETE.
- PID e GPIO operam a partir de snapshots em memória, nunca consultam o banco
  a cada amostra.
- Mudanças de hardware exigem validação, aprovação e reinício seguro.
- Migração de estado interrompido não reativa atuadores automaticamente.
- Recuperação: a versão estável permanece em seu próprio diretório e seus
  YAML/JSON não são modificados pelo importador.
- Backup SQLite: `python -m storage.cli backup --output backups/bridge-backup.sqlite3`

## Testes

```bash
python -m compileall -q .
python -m pytest -q tests/test_data_store.py tests/test_storage_legacy_import.py \
  tests/test_sqlite_admin.py tests/test_recipe_engine.py tests/test_device_runtime.py
```

Ainda é necessário homologar resultados de teste e cenário físico.
Não faça merge para `main` até a bateria completa passar e validar
o Raspberry Pi com cargas desconectadas e água.
