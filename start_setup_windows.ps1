
$ErrorActionPreference = "Stop"

$repo = "https://github.com/ChristopherNicolasSMM/Tesseract-Device-Bridge.git"
$branch = "feature/sqlite-full-migration"
$folder = "Tesseract-Device-Bridge-SQLite"

try {
    # Verificar dependências
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "Git não encontrado. Instale o Git antes de continuar."
    }

    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "Python não encontrado. Instale o Python antes de continuar."
    }

    # Clonar repositório
    if (-not (Test-Path $folder)) {
        Write-Host "Clonando repositório..." -ForegroundColor Cyan
        git clone --branch $branch --single-branch $repo $folder
        if ($LASTEXITCODE -ne 0) {
            throw "Falha ao clonar o repositório."
        }
    }
    else {
        Write-Host "Pasta existente. Clone ignorado." -ForegroundColor Yellow
    }

    Set-Location $folder

    # Criar ambiente virtual
    if (-not (Test-Path ".\venv\Scripts\python.exe")) {
        Write-Host "Criando ambiente virtual..." -ForegroundColor Cyan
        python -m venv venv
        if ($LASTEXITCODE -ne 0) {
            throw "Falha ao criar o ambiente virtual."
        }
    }

    # Usar Python diretamente do ambiente virtual
    # Evita problemas com ExecutionPolicy do PowerShell
    $python = ".\venv\Scripts\python.exe"

    # Instalar dependências
    Write-Host "Instalando dependências..." -ForegroundColor Cyan
    & $python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        throw "Falha ao instalar dependências."
    }

    # Executar setup
    Write-Host "Iniciando setup..." -ForegroundColor Green
    & $python -m setup
    if ($LASTEXITCODE -ne 0) {
        throw "O setup terminou com erro."
    }

    Write-Host "Setup finalizado com sucesso!" -ForegroundColor Green
}
catch {
    Write-Host ""
    Write-Host "ERRO: $($_.Exception.Message)" -ForegroundColor Red
}
finally {
    Write-Host ""
    Read-Host "Pressione ENTER para sair"
}
