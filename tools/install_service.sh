#!/usr/bin/env bash
# =============================================================================
# install_service.sh — Instala o Tesseract Device Bridge como serviço systemd
# =============================================================================
#
# O que este script faz
# ---------------------
#   1. Detecta (ou pede) o usuário que vai rodar o serviço
#   2. Detecta o diretório do projeto e o caminho do Python
#   3. Gera e instala /etc/systemd/system/tesseract-bridge.service
#   4. Habilita o serviço para iniciar no boot
#   5. Cria ~/.config/autostart/tesseract-bridge-logs.desktop
#      para abrir o lxterminal com logs ao vivo quando o LXDE carregar
#
# Uso
# ---
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

info()    { echo -e "${_G}[INFO]${_RST}  $*"; }
warn()    { echo -e "${_Y}[WARN]${_RST}  $*"; }
error()   { echo -e "${_R}[ERRO]${_RST}  $*" >&2; }
titulo()  { echo -e "\n${_B}${_C}$*${_RST}\n"; }

# ---- verificar se está rodando com sudo ------------------------------------
if [ "$EUID" -ne 0 ]; then
    error "Este script precisa ser executado com sudo:"
    echo "    sudo bash tools/install_service.sh"
    exit 1
fi

titulo "=== Tesseract Device Bridge — Instalação do Serviço ==="

# ---- detectar diretório do projeto -----------------------------------------
# O projeto está um nível acima de tools/, então usamos o diretório do script.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
info "Diretório do projeto detectado: ${_C}$PROJECT_DIR${_RST}"

# ---- detectar usuário -------------------------------------------------------
# Estratégia: SUDO_USER (quem rodou o sudo) tem prioridade, porque "root"
# não é o usuário certo para rodar o bridge. Se não houver SUDO_USER,
# tentamos logname (usuário logado no terminal). Depois perguntamos.
if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
    AUTO_USER="$SUDO_USER"
    AUTO_SOURCE="(detectado via SUDO_USER — quem rodou o sudo)"
else
    AUTO_USER="$(logname 2>/dev/null || echo "")"
    if [ -n "$AUTO_USER" ] && [ "$AUTO_USER" != "root" ]; then
        AUTO_SOURCE="(detectado via logname)"
    else
        AUTO_USER=""
        AUTO_SOURCE=""
    fi
fi

echo ""
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

# Validar que o usuário existe
if ! id "$SERVICE_USER" &>/dev/null; then
    error "Usuário '$SERVICE_USER' não existe no sistema."
    exit 1
fi

SERVICE_HOME="$(eval echo "~$SERVICE_USER")"
info "Serviço vai rodar como: ${_C}$SERVICE_USER${_RST} (home: $SERVICE_HOME)"

# ---- detectar Python -------------------------------------------------------
# Procura na seguinte ordem:
#   1. .venv/bin/python3 dentro do projeto (ambiente virtual)
#   2. python3 no PATH do usuário do serviço
#   3. python3 global
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python3"
if [ -x "$VENV_PYTHON" ]; then
    PYTHON_BIN="$VENV_PYTHON"
    info "Python detectado: ${_C}$PYTHON_BIN${_RST} (venv)"
else
    PYTHON_BIN="$(su -s /bin/bash "$SERVICE_USER" -c "which python3 2>/dev/null" || which python3)"
    info "Python detectado: ${_C}$PYTHON_BIN${_RST}"
fi

if [ ! -x "$PYTHON_BIN" ]; then
    error "Python não encontrado. Instale com: sudo apt install python3"
    exit 1
fi

# ---- gerar arquivo de serviço ----------------------------------------------
SERVICE_NAME="tesseract-bridge"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

info "Gerando $SERVICE_FILE ..."

cat > "$SERVICE_FILE" << SERVICE
[Unit]
Description=Tesseract Device Bridge
# Aguarda a rede estar disponível antes de iniciar (necessário para MQTT)
After=network.target
# Se o MQTT broker estiver no mesmo Pi, inicia depois dele
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR

# FORCE_COLOR=1 faz o bridge emitir cores ANSI mesmo sem TTY.
# O journald preserva esses códigos e o logs.sh usa --output=cat
# para mostrá-los coloridos no terminal.
Environment=FORCE_COLOR=1

ExecStart=$PYTHON_BIN $PROJECT_DIR/run_bridge.py

# Reinicia automaticamente se o processo cair por erro (mas não se
# for parado manualmente com systemctl stop).
Restart=on-failure
RestartSec=5

# Captura stdout e stderr no journal (journalctl -fu tesseract-bridge)
StandardOutput=journal
StandardError=journal

[Install]
# multi-user.target = boot normal sem desktop; garante que o serviço
# inicia antes do LXDE também, não só em modo headless.
WantedBy=multi-user.target
SERVICE

info "Serviço criado."

# ---- habilitar serviço -----------------------------------------------------
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
info "Serviço habilitado para iniciar no boot."

# Pergunta se quer iniciar agora
echo ""
read -rp "  Iniciar o serviço agora? [S/n]: " START_NOW
START_NOW="${START_NOW:-s}"
if [[ "$START_NOW" =~ ^[SsYy]$ ]]; then
    systemctl start "$SERVICE_NAME"
    sleep 1
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        info "Serviço iniciado com sucesso! ✓"
    else
        warn "Serviço pode não ter iniciado corretamente."
        warn "Verifique com: sudo systemctl status $SERVICE_NAME"
    fi
fi

# ---- autostart LXDE (abre lxterminal com logs no boot do desktop) ----------
AUTOSTART_DIR="$SERVICE_HOME/.config/autostart"
AUTOSTART_FILE="$AUTOSTART_DIR/tesseract-bridge-logs.desktop"

echo ""
read -rp "  Criar autostart LXDE (abre terminal de logs ao iniciar o desktop)? [S/n]: " CREATE_AUTOSTART
CREATE_AUTOSTART="${CREATE_AUTOSTART:-s}"

if [[ "$CREATE_AUTOSTART" =~ ^[SsYy]$ ]]; then
    mkdir -p "$AUTOSTART_DIR"

    cat > "$AUTOSTART_FILE" << DESKTOP
[Desktop Entry]
Type=Application
Name=Tesseract Bridge — Logs
Comment=Abre o terminal de logs do Tesseract Device Bridge automaticamente
# Aguarda 3s para o serviço subir antes de abrir o terminal de logs.
# O 'exec bash' no final mantém o terminal aberto mesmo se o journalctl sair.
Exec=bash -c 'sleep 3 && lxterminal --title="Tesseract Bridge — Logs" -e "bash -c \"journalctl -fu tesseract-bridge --output=cat --no-pager; exec bash\""'
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
DESKTOP

    # O arquivo deve pertencer ao usuário do serviço, não ao root
    chown "$SERVICE_USER:$SERVICE_USER" "$AUTOSTART_FILE"
    info "Autostart LXDE criado: $AUTOSTART_FILE"
    info "Na próxima vez que o desktop carregar, o terminal de logs abrirá automaticamente."
fi

# ---- resumo ----------------------------------------------------------------
titulo "=== Instalação concluída ==="
echo -e "  Serviço:     ${_C}$SERVICE_NAME${_RST}"
echo -e "  Usuário:     ${_C}$SERVICE_USER${_RST}"
echo -e "  Projeto:     ${_C}$PROJECT_DIR${_RST}"
echo -e "  Python:      ${_C}$PYTHON_BIN${_RST}"
echo ""
echo -e "  ${_B}Comandos úteis:${_RST}"
echo -e "    ${_Y}bash tools/logs.sh${_RST}                   # logs ao vivo no terminal atual"
echo -e "    ${_Y}sudo systemctl status $SERVICE_NAME${_RST}    # status do serviço"
echo -e "    ${_Y}sudo systemctl stop   $SERVICE_NAME${_RST}    # parar"
echo -e "    ${_Y}sudo systemctl start  $SERVICE_NAME${_RST}    # iniciar"
echo -e "    ${_Y}sudo systemctl restart $SERVICE_NAME${_RST}   # reiniciar"
echo -e "    ${_Y}sudo bash tools/uninstall_service.sh${_RST}   # desinstalar"
echo ""
