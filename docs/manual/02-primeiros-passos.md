# 02 — Primeiros passos | Device Bridge 2.0.0

O fluxo atual é: clone novo → venv/dependências → python -m setup → navegador.
Não depende de .env, SQLite ou instalação antiga.

Leia o [Manual de Instalação e Migração consolidado](20-instalacao-migracao-2.0.0.md)
para todas as plataformas, importação, credenciais e recuperação.

## Windows / PowerShell

```powershell
git clone --branch feature/sqlite-full-migration --single-branch https://github.com/ChristopherNicolasSMM/Tesseract-Device-Bridge.git Tesseract-Device-Bridge-SQLite
cd Tesseract-Device-Bridge-SQLite
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m setup
```

## Linux / Raspberry

```bash
git clone --branch feature/sqlite-full-migration --single-branch https://github.com/ChristopherNicolasSMM/Tesseract-Device-Bridge.git Tesseract-Device-Bridge-SQLite
cd Tesseract-Device-Bridge-SQLite
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python -m setup
```

Setup e simulação aceitam o ambiente Python suportado pelas dependências.
GPIO real continua exigindo a venv Python 3.9 do Raspberry. Escolha esse ambiente
antes de concluir em modo físico, sem trocar o Python do sistema.
O setup não exige root.

## Assistente

Abra http://127.0.0.1:8090 e confira build 2.0.0-setup.11.
Selecione idioma/aparência e escolha banco vazio, arquivos antigos ou SQLite.
Revise inventário/relatórios; configure infraestrutura e credencial.
Conclua com seleção explícita de candidato e consentimentos aplicáveis.

Banco novo não contém dispositivos fictícios. Sem devices, o início abre somente
administração de configuração, sem GPIO/MQTT. Com pendências, a operação física
permanece bloqueada. Setup concluído não inicia o runtime automaticamente.

```powershell
python -m setup.doctor
python run_bridge.py
```

O painel simulado usa 127.0.0.1:8089 por padrão. O setup usa outra porta (8090).

## Compatibilidade

storage.cli init e o migrador antigo permanecem para instalações legacy/sandboxes.
O seed demonstrativo desse caminho não é o bootstrap ORM do setup.
Não rode esses comandos sobre a instalação já publicada.

A main e a pasta antiga continuam preservadas. Não faça merge em main sem
solicitação explícita e não execute duas instâncias físicas sobre a mesma planta.
