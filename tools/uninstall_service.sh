#!/usr/bin/env bash
# =============================================================================
# uninstall_service.sh — Remove o serviço Tesseract Device Bridge
# =============================================================================
#
# Uso:
#   sudo bash tools/uninstall_service.sh
#
# O que remove:
#   - /etc/systemd/system/tesseract-bridge.service
#   - ~/.config/autostart/tesseract-bridge-logs.desktop (do usuário correto)
#
# O que NÃO remove (dados do usuário):
#   - data/ inteira (devices.yml, receitas, estado de execução)
#   - O código do projeto em si
# =============================================================================

set -euo pipefail

_G="\e[92m"; _Y="\e[93m"; _R="\e[91m"; _C="\e[96m"; _B="\e[1m"; _RST="\e[0m"
info()  { echo -e "${_G}[INFO]${_RST}  $*"; }
warn()  { echo -e "${_Y}[WARN]${_RST}  $*"; }
error() { echo -e "${_R}[ERRO]${_RST}  $*" >&2; }

if [ "$EUID" -ne 0 ]; then
    error "Execute com sudo: sudo bash tools/uninstall_service.sh"
    exit 1
fi

echo -e "\n${_B}${_C}=== Tesseract Device Bridge — Remoção do Serviço ===${_RST}\n"

SERVICE_NAME="tesseract-bridge"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# Parar e desabilitar o serviço se estiver ativo
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    info "Parando o serviço..."
    systemctl stop "$SERVICE_NAME"
fi

if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
    info "Desabilitando o serviço..."
    systemctl disable "$SERVICE_NAME"
fi

# Remover o arquivo de serviço
if [ -f "$SERVICE_FILE" ]; then
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload
    info "Arquivo de serviço removido: $SERVICE_FILE"
else
    warn "Arquivo de serviço não encontrado (já removido?): $SERVICE_FILE"
fi

# Remover autostart LXDE de todos os usuários que o tenham
# (procura no home de todos os usuários com home em /home/*)
FOUND_AUTOSTART=0
for USER_HOME in /home/*/; do
    AUTOSTART="$USER_HOME/.config/autostart/tesseract-bridge-logs.desktop"
    if [ -f "$AUTOSTART" ]; then
        USERNAME="$(basename "$USER_HOME")"
        rm -f "$AUTOSTART"
        info "Autostart LXDE removido para $USERNAME: $AUTOSTART"
        FOUND_AUTOSTART=1
    fi
done
# Verificar também o home do root (improvável mas seguro)
ROOT_AUTOSTART="/root/.config/autostart/tesseract-bridge-logs.desktop"
if [ -f "$ROOT_AUTOSTART" ]; then
    rm -f "$ROOT_AUTOSTART"
    info "Autostart LXDE removido para root."
    FOUND_AUTOSTART=1
fi

if [ "$FOUND_AUTOSTART" -eq 0 ]; then
    warn "Nenhum autostart LXDE encontrado (já removido ou nunca criado)."
fi

echo ""
info "Desinstalação concluída."
info "Os arquivos de dados (pasta data/) foram preservados."
echo ""
