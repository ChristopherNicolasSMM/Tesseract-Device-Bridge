# 02 — Primeiros passos | Tesseract Device Bridge 2.0.0

> **Estado:** versão 2.0.0 em homologação na branch `feature/sqlite-full-migration`. A `main` permanece estável na arquitetura anterior. Não execute duas instâncias com GPIO real na mesma planta.

## Requisitos

- Python **3.9.x** na virtualenv do Raspberry Pi para `backend=real`. No Windows, utilize o Python suportado pelo ambiente de testes e **sempre** `SIMULATION_ONLY=1`.
- Git e dependências em `requirements.txt`.
- Para importar instalações antigas: cópia íntegra dos arquivos YAML/JSON (incluindo `data/private/`) feita com a operação parada.
- Um SQLite é usado por instalação, em `data/private/*.sqlite3`; não é necessário servidor de banco.

## 1. Clonar a versão experimental

**Windows PowerShell**:

```powershell
git clone --branch feature/sqlite-full-migration --single-branch https://github.com/ChristopherNicolasSMM/Tesseract-Device-Bridge.git Tesseract-Device-Bridge-SQLite
cd Tesseract-Device-Bridge-SQLite
py -3.9 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

**Raspberry Pi (somente clone isolado, sem GPIO real nesta etapa)**:

```bash
git clone --branch feature/sqlite-full-migration --single-branch https://github.com/ChristopherNicolasSMM/Tesseract-Device-Bridge.git Tesseract-Device-Bridge-SQLite
cd Tesseract-Device-Bridge-SQLite
python3.9 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
```

## 2. Criar o .env de infraestrutura

Windows: `Copy-Item .env.example .env` e `notepad .env`.
Linux: `cp .env.example .env`, edite o arquivo e execute `chmod 600 .env`.

Para criar o token administrativo:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Exemplo seguro para homologação:

```dotenv
TESSERACT_BRIDGE_DB=./data/private/imported.sqlite3
TESSERACT_BRIDGE_SIMULATION_ONLY=1
TESSERACT_BRIDGE_TEST_PANEL_PORT=8089
TESSERACT_BRIDGE_PANEL_HOST=
TESSERACT_BRIDGE_PANEL_PORT=
TESSERACT_BRIDGE_ADMIN_TOKEN=SEU_TOKEN_PRIVADO_GERADO
```

O `.env` **não é versionado** e é carregado automaticamente pelos entrypoints e pela CLI. A variável já definida no sistema/PowerShell prevalece sobre o `.env`. O caminho relativo do banco é resolvido a partir da pasta da instalação.

## 3. Escolher: instalação vazia ou importação

**Instalação vazia:** altere `TESSERACT_BRIDGE_DB=./data/private/bridge.sqlite3` e execute:

```powershell
python -m storage.cli init
python -m storage.cli status
```

O banco inicia em simulação com **um sensor demonstrativo e nenhuma receita**.

**Migração de dados antigos:** mantenha `imported.sqlite3` no `.env` e siga [Migração SQLite](12-sqlite-migracao.md). Valide primeiro com `--dry-run`. A importação exige banco de destino inexistente e backup; não altera a pasta original.

No caso de atuadores legados com `remote_control: true` mas sem `state_topic` (ex.: `pump_b1`), o importador exige correção da cópia de origem **ou** o parâmetro explícito `--disable-invalid-remote-control`, que desabilita apenas a permissão remota incompatível e registra a adaptação.

## 4. Testar antes de abrir o painel

```powershell
python -m compileall -q .
python -m pytest -q tests/test_infra_env.py tests/test_storage_legacy_import.py tests/test_data_store.py tests/test_sqlite_admin.py
python -m storage.cli status
```

Confirme `db`, `backend_runtime=simulated`, `mqtt_runtime_enabled=false`, `panel_runtime_host=127.0.0.1` e `panel_runtime_port=8089`.

## 5. Abrir o Bridge no Windows

```powershell
python run_bridge.py
```

Abra `http://127.0.0.1:8089` no mesmo computador. No modo simulado, o backend real é substituído apenas **em memória** e MQTT fica desligado. A configuração importada no SQLite é preservada.

- **Painel:** sensores, atuadores e telemetria simulados.
- **Gerenciamento:** inventário **somente leitura** do snapshot em execução; abaixo fica a **Administração SQLite**.
- **Receitas:** execução e etapas.
- **Configurações:** controle térmico e calibrações individuais.
- **Cadastro:** catálogo de receitas e seleção para o próximo boot.

## 6. Administrar dispositivos e parâmetros

Em **Gerenciamento → Administração SQLite**, informe o `TESSERACT_BRIDGE_ADMIN_TOKEN` (valor do `.env`) e clique **Desbloquear**. O token é uma credencial administrativa da API, **não** uma senha do arquivo SQLite.

Para mudar nome, GPIO, sensor ou conectividade: **editar → atualizar o dispositivo no rascunho → salvar rascunho validado → aprovar para próximo boot → parar a operação → reiniciar em condição segura**. Não existe hot reload de GPIO em operação. Calibrações e receitas possuem telas próprias.

**Para o primeiro teste**, altere somente o nome de um dispositivo, aprove a revisão, encerre a simulação, reinicie e confira o nome. Não habilite GPIO real, GLP ou saídas físicas.

## 7. Backup, retorno e serviço

```powershell
python -m storage.cli backup --output backups/antes-validacao.sqlite3
```

O botão **Backup SQLite** da Administração também cria uma cópia consistente. Guarde cópia externa, com acesso restrito. Para reverter, encerre o clone e utilize a pasta `main`/YAML/JSON anterior, que a importação não modifica.

O `tools/install_service.sh` é específico do Linux e deve ser usado **somente depois** de homologar Raspberry Pi, permissões, portas e watchdog do serviço. Para GPIO real mantenha Python 3.9, certifique-se de que a instância antiga está parada e faça testes elétricos seguros antes de ligar cargas.

## Próximas leituras

- [Administração SQLite e segurança](13-administracao-sqlite.md)
- [Migração e recuperação](12-sqlite-migracao.md)
- [Funcionalidades](03-funcionalidades.md)
- [Modelo de dados SQLite](../technical/04-modelo-de-dados.md)
