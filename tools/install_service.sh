#!/usr/bin/env bash
# =============================================================================
# install_service.sh — Instala o Tesseract Device Bridge como serviço systemd
# =============================================================================
#
# IMPORTANTE: este script é exclusivo do Linux (systemd).
#   No Windows: use Task Scheduler ou execute python run_bridge.py manualmente.
#   No Mac:     use launchd (fora do escopo deste projeto).
#
# O que este script faz:
#   1. Verifica que está no Linux
#   2. Detecta (ou pede) o usuário que vai rodar o serviço
#   3. Detecta o diretório do projeto e confirma que devices.yml existe
#   4. Detecta e valida o Python/venv — testa imports críticos antes de criar
#      o serviço (evita serviço que falha silenciosamente por venv errada)
#   5. Gera e instala /etc/systemd/system/tesseract-bridge.service
#      com ExecStart correto para ativar a venv
#   6. Habilita o serviço para iniciar no boot
#   7. Cria ~/.config/autostart/tesseract-bridge-logs.desktop (LXDE)
#
# Uso:
#   sudo bash tools/install_service.sh
#
# Para desinstalar:
#   sudo bash tools/uninstall_service.sh
#
# Para ver os logs ao vivo depois de instalado:
#   bash tools/logs.sh
# =============================================================================

set -euo pipefail

# ---- cores para o output do script ----------------------------------------
_G="\e[92m"   # verde
_Y="\e[93m"   # amarelo
_R="\e[91m"   # vermelho
_C="\e[96m"   # ciano
_B="\e[1m"    # bold
_RST="\e[0m"

info()   { echo -e "${_G}[INFO]${_RST}  $*"; }
warn()   { echo -e "${_Y}[WARN]${_RST}  $*"; }
error()  { echo -e "${_R}[ERRO]${_RST}  $*" >&2; }
titulo() { echo -e "\n${_B}${_C}$*${_RST}\n"; }
ok()     { echo -e "  ${_G}✓${_RST} $*"; }
fail()   { echo -e "  ${_R}✗${_RST} $*"; }

# ---- verificar OS ----------------------------------------------------------
if [[ "$OSTYPE" != "linux"* ]]; then
    error "Este script requer Linux (systemd)."
    echo ""
    echo "  No Windows: use Task Scheduler ou execute manualmente:"
    echo "    python run_bridge.py"
    echo ""
    echo "  No Mac: use launchd (fora do escopo deste projeto)."
    exit 1
fi

# ---- verificar sudo --------------------------------------------------------
if [ "$EUID" -ne 0 ]; then
    error "Este script precisa ser executado com sudo:"
    echo "    sudo bash tools/install_service.sh"
    exit 1
fi

titulo "=== Tesseract Device Bridge — Instalação do Serviço ==="

# ---- detectar diretório do projeto -----------------------------------------
# BASH_SOURCE[0] é o caminho deste script (tools/install_service.sh)
# O projeto está um nível acima de tools/
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

info "Diretório do projeto: ${_C}$PROJECT_DIR${_RST}"

# Confirmar que este é de fato o diretório certo (run_bridge.py deve existir)
if [ ! -f "$PROJECT_DIR/run_bridge.py" ]; then
    error "run_bridge.py não encontrado em $PROJECT_DIR"
    error "Execute o script de DENTRO do repositório:"
    echo "    cd /caminho/para/Tesseract-Device-Bridge"
    echo "    sudo bash tools/install_service.sh"
    exit 1
fi
ok "run_bridge.py encontrado"

# Verificar devices.yml
if [ ! -f "$PROJECT_DIR/devices.yml" ]; then
    warn "devices.yml não encontrado. Será criado a partir do exemplo no primeiro boot."
    warn "Recomendado: configure o devices.yml antes de iniciar o serviço."
else
    ok "devices.yml encontrado"
fi

# ---- detectar usuário -------------------------------------------------------
# SUDO_USER é quem rodou o sudo (não root) — é o usuário correto para o serviço
echo ""
if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
    AUTO_USER="$SUDO_USER"
    AUTO_SOURCE="(detectado via SUDO_USER)"
else
    AUTO_USER="$(logname 2>/dev/null || echo "")"
    if [ -n "$AUTO_USER" ] && [ "$AUTO_USER" != "root" ]; then
        AUTO_SOURCE="(detectado via logname)"
    else
        AUTO_USER=""
        AUTO_SOURCE=""
    fi
fi

if [ -n "$AUTO_USER" ]; then
    echo -e "  Usuário detectado: ${_C}${_B}$AUTO_USER${_RST} $AUTO_SOURCE"
    echo ""
    echo -e "  [1] Usar ${_C}$AUTO_USER${_RST} ${_G}← recomendado${_RST}"
    echo "  [2] Digitar outro usuário"
    echo ""
    read -rp "  Escolha [1]: " USER_CHOICE
    USER_CHOICE="${USER_CHOICE:-1}"

    if [ "$USER_CHOICE" = "2" ]; then
        read -rp "  Usuário: " SERVICE_USER
        SERVICE_USER="${SERVICE_USER:-$AUTO_USER}"
    else
        SERVICE_USER="$AUTO_USER"
    fi
else
    warn "Não foi possível detectar o usuário automaticamente."
    read -rp "  Digite o usuário que vai rodar o serviço: " SERVICE_USER
    if [ -z "$SERVICE_USER" ]; then
        error "Usuário não pode ser vazio."
        exit 1
    fi
fi

if ! id "$SERVICE_USER" &>/dev/null; then
    error "Usuário '$SERVICE_USER' não existe no sistema."
    exit 1
fi

SERVICE_HOME="$(eval echo "~$SERVICE_USER")"
ok "Serviço vai rodar como: $SERVICE_USER (home: $SERVICE_HOME)"

# ---- detectar Python e venv ------------------------------------------------
# Ordem de preferência:
#   1. .venv dentro do projeto (virtualenv local — mais confiável)
#   2. venv dentro do projeto (nome alternativo comum)
#   3. python3 do usuário do serviço (PATH do usuário, não do root)
#   4. python3 global
#
# CRÍTICO: quando há venv, o ExecStart deve ATIVAR a venv, não só
# apontar para o binário python3 da venv. Isso garante que PYTHONPATH
# e as variáveis de ambiente da venv estão corretas durante a execução.

VENV_DIR=""
PYTHON_BIN=""
ACTIVATE_CMD=""

# Tentar .venv
if [ -f "$PROJECT_DIR/.venv/bin/activate" ]; then
    VENV_DIR="$PROJECT_DIR/.venv"
    info "Venv detectada: ${_C}$VENV_DIR${_RST}"
# Tentar venv
elif [ -f "$PROJECT_DIR/venv/bin/activate" ]; then
    VENV_DIR="$PROJECT_DIR/venv"
    info "Venv detectada: ${_C}$VENV_DIR${_RST}"
fi

if [ -n "$VENV_DIR" ]; then
    PYTHON_BIN="$VENV_DIR/bin/python3"
    # O ExecStart vai source o activate antes de rodar — garante
    # que todas as variáveis de ambiente da venv estão disponíveis
    ACTIVATE_CMD="source $VENV_DIR/bin/activate && "
    ok "Venv encontrada: $VENV_DIR"
else
    warn "Nenhuma venv encontrada no projeto (nem .venv/ nem venv/)."
    warn "Usando Python global — os pacotes precisam estar instalados globalmente."
    # Pegar python3 do contexto do usuário do serviço (não do root)
    PYTHON_BIN="$(su -s /bin/bash "$SERVICE_USER" -c "which python3 2>/dev/null" || which python3 2>/dev/null || echo "")"
    ACTIVATE_CMD=""
fi

if [ -z "$PYTHON_BIN" ] || [ ! -x "$PYTHON_BIN" ]; then
    error "Python não encontrado."
    echo "  Instale com: sudo apt install python3"
    exit 1
fi

PYTHON_VERSION="$("$PYTHON_BIN" --version 2>&1)"
ok "Python: $PYTHON_BIN ($PYTHON_VERSION)"

# ---- testar imports críticos ANTES de criar o serviço ----------------------
# Se os imports falharem, o serviço vai criar e falhar silenciosamente.
# Melhor falhar aqui com mensagem clara.
titulo "=== Verificando dependências Python ==="

IMPORT_ERRORS=0

check_import() {
    local pkg="$1"
    local install_hint="${2:-pip install $1}"
    if "$PYTHON_BIN" -c "import $pkg" 2>/dev/null; then
        ok "$pkg"
    else
        fail "$pkg — AUSENTE"
        echo "       Instale com: $install_hint"
        IMPORT_ERRORS=$((IMPORT_ERRORS + 1))
    fi
}

# Se há venv, ativar antes de checar os imports
if [ -n "$VENV_DIR" ]; then
    # shellcheck source=/dev/null
    source "$VENV_DIR/bin/activate"
    PYTHON_BIN="$(which python3)"
    info "Venv ativada para verificação de imports"
fi

check_import "flask"     "pip install flask"
check_import "paho.mqtt" "pip install paho-mqtt"
check_import "yaml"      "pip install PyYAML"
check_import "gpiozero"  "pip install gpiozero"

if [ $IMPORT_ERRORS -gt 0 ]; then
    echo ""
    error "$IMPORT_ERRORS dependência(s) ausente(s)."
    if [ -n "$VENV_DIR" ]; then
        echo ""
        echo "  Com a venv ativa, instale assim:"
        echo "    source $VENV_DIR/bin/activate"
        echo "    pip install -r $PROJECT_DIR/requirements.txt"
    else
        echo ""
        echo "  Instale assim:"
        echo "    pip install -r $PROJECT_DIR/requirements.txt"
    fi
    echo ""
    read -rp "  Continuar mesmo assim? [s/N]: " FORCE
    FORCE="${FORCE:-n}"
    if [[ ! "$FORCE" =~ ^[SsYy]$ ]]; then
        echo "  Instalação cancelada."
        exit 1
    fi
    warn "Continuando com dependências ausentes — o serviço pode falhar ao iniciar."
fi

# Restaurar python_bin correto para o arquivo de serviço
if [ -n "$VENV_DIR" ]; then
    PYTHON_BIN="$VENV_DIR/bin/python3"
fi

# ---- criar pasta de log de boot --------------------------------------------
# O run_bridge.py tenta gravar em /var/log/tesseract-bridge/boot.log
# para registrar falhas de inicialização antes do logging Python subir.
# Criar a pasta aqui garante que o serviço tem permissão de escrita.
LOG_DIR="/var/log/tesseract-bridge"
mkdir -p "$LOG_DIR"
chown "$SERVICE_USER:$SERVICE_USER" "$LOG_DIR"
ok "Pasta de log criada: $LOG_DIR"
info "Boot log disponível em: ${_C}$LOG_DIR/boot.log${_RST}"

# ---- gerar arquivo de serviço ----------------------------------------------
titulo "=== Gerando arquivo de serviço ==="

SERVICE_NAME="tesseract-bridge"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# O ExecStart usa bash -c para:
#   1. source o activate da venv (se houver) — ativa PYTHONPATH e variáveis
#   2. cd para o PROJECT_DIR — garante que devices.yml e recipe.yml são
#      encontrados como caminhos relativos
#   3. exec python3 run_bridge.py — exec substitui o bash pelo Python,
#      sem processo filho extra (o PID do serviço é o Python diretamente)
if [ -n "$ACTIVATE_CMD" ]; then
    EXEC_START="/bin/bash -c '${ACTIVATE_CMD}cd $PROJECT_DIR && exec python3 run_bridge.py'"
    EXEC_DESCRIPTION="bash -c source venv + python3 run_bridge.py"
else
    EXEC_START="/bin/bash -c 'cd $PROJECT_DIR && exec $PYTHON_BIN run_bridge.py'"
    EXEC_DESCRIPTION="bash -c cd + python3 run_bridge.py"
fi

ok "ExecStart: $EXEC_DESCRIPTION"
ok "WorkingDirectory: $PROJECT_DIR"

cat > "$SERVICE_FILE" << SERVICE
[Unit]
Description=Tesseract Device Bridge
Documentation=https://github.com/ChristopherNicolasSMM/Tesseract-Device-Bridge
# Aguarda a rede antes de iniciar (necessário para MQTT)
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
# WorkingDirectory garante que devices.yml e recipe.yml são encontrados
# como caminhos relativos ao diretório do projeto
WorkingDirectory=$PROJECT_DIR

# FORCE_COLOR=1: faz o bridge emitir cores ANSI mesmo sem TTY.
# O journald preserva os códigos e logs.sh usa --output=cat para mostrar.
# PYTHONUNBUFFERED=1: desativa o buffer de stdout/stderr do Python —
# garante que os logs aparecem em tempo real no journal (sem buffer).
Environment=FORCE_COLOR=1
Environment=PYTHONUNBUFFERED=1

# ExecStart usa bash para:
#   1. source a venv (se houver) — ativa PYTHONPATH e dependências
#   2. cd para o projeto — garante caminhos relativos corretos
#   3. exec python3 — substitui o bash pelo Python (PID limpo)
ExecStart=$EXEC_START

# Reinicia após falha (mas não após systemctl stop manual)
Restart=on-failure
RestartSec=5

# Captura stdout e stderr no journal
StandardOutput=journal
StandardError=journal

[Install]
# multi-user.target: inicia no boot normal, antes e depois do desktop LXDE
WantedBy=multi-user.target
SERVICE

ok "Arquivo de serviço criado: $SERVICE_FILE"

# ---- habilitar serviço -----------------------------------------------------
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
ok "Serviço habilitado para iniciar no boot"

# Pergunta se quer iniciar agora
echo ""
read -rp "  Iniciar o serviço agora? [S/n]: " START_NOW
START_NOW="${START_NOW:-s}"
if [[ "$START_NOW" =~ ^[SsYy]$ ]]; then
    systemctl start "$SERVICE_NAME"
    sleep 2
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        ok "Serviço iniciado com sucesso!"
    else
        warn "Serviço não iniciou corretamente."
        echo ""
        echo "  Diagnóstico rápido:"
        echo "    sudo systemctl status $SERVICE_NAME"
        echo "    sudo journalctl -u $SERVICE_NAME -n 50"
        echo "    cat $LOG_DIR/boot.log"
        echo ""
        # Mostrar as últimas linhas do status automaticamente
        systemctl status "$SERVICE_NAME" --no-pager -n 20 || true
    fi
fi

# ---- autostart LXDE --------------------------------------------------------
AUTOSTART_DIR="$SERVICE_HOME/.config/autostart"
AUTOSTART_FILE="$AUTOSTART_DIR/tesseract-bridge-logs.desktop"

echo ""
read -rp "  Criar autostart LXDE (terminal de logs ao iniciar o desktop)? [S/n]: " CREATE_AUTOSTART
CREATE_AUTOSTART="${CREATE_AUTOSTART:-s}"

if [[ "$CREATE_AUTOSTART" =~ ^[SsYy]$ ]]; then
    mkdir -p "$AUTOSTART_DIR"
    cat > "$AUTOSTART_FILE" << DESKTOP
[Desktop Entry]
Type=Application
Name=Tesseract Bridge — Logs
Comment=Abre o terminal de logs do Tesseract Device Bridge automaticamente
Exec=bash -c 'sleep 3 && lxterminal --title="Tesseract Bridge — Logs" -e "bash -c \"journalctl -fu tesseract-bridge --output=cat --no-pager; exec bash\""'
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
DESKTOP
    chown "$SERVICE_USER:$SERVICE_USER" "$AUTOSTART_FILE"
    ok "Autostart LXDE criado: $AUTOSTART_FILE"
fi

# ---- resumo ----------------------------------------------------------------
titulo "=== Instalação concluída ==="
echo -e "  Serviço:        ${_C}$SERVICE_NAME${_RST}"
echo -e "  Usuário:        ${_C}$SERVICE_USER${_RST}"
echo -e "  Projeto:        ${_C}$PROJECT_DIR${_RST}"
echo -e "  Python/venv:    ${_C}${VENV_DIR:-python3 global}${_RST}"
echo -e "  Boot log:       ${_C}$LOG_DIR/boot.log${_RST}"
echo ""
echo -e "  ${_B}Comandos úteis:${_RST}"
echo -e "    ${_Y}bash tools/logs.sh${_RST}                      # logs ao vivo"
echo -e "    ${_Y}cat $LOG_DIR/boot.log${_RST}  # log de inicialização"
echo -e "    ${_Y}sudo systemctl status $SERVICE_NAME${_RST}     # status"
echo -e "    ${_Y}sudo systemctl restart $SERVICE_NAME${_RST}    # reiniciar"
echo -e "    ${_Y}sudo systemctl stop $SERVICE_NAME${_RST}       # parar"
echo -e "    ${_Y}sudo bash tools/uninstall_service.sh${_RST}    # desinstalar"
echo ""
echo -e "  ${_B}Se o serviço não iniciar:${_RST}"
echo -e "    ${_Y}cat $LOG_DIR/boot.log${_RST}  # veja onde parou"
echo -e "    ${_Y}sudo journalctl -u $SERVICE_NAME -n 50${_RST}  # journal completo"
echo ""
