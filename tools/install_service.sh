#!/usr/bin/env bash
# =============================================================================
# install_service.sh — Instala o Tesseract Device Bridge como serviço systemd
# =============================================================================
#
# Linux / systemd
#
# O que este script faz:
#   1. Verifica Linux + systemd + sudo
#   2. Detecta o usuário que executará o serviço
#   3. Detecta o diretório do projeto
#   4. Detecta .venv/ ou venv/ e SEMPRE usa a venv quando encontrada
#   5. Valida dependências Python
#   6. Cria o serviço tesseract-bridge.service
#   7. Configura restart automático + proteção contra restart storm
#   8. Cria watchdog periódico para detectar bridge sem resposta
#   9. Cria o launcher do Chromium em modo kiosk
#  10. Configura o kiosk para abrir somente depois que o bridge responder
#  11. Configura o bridge para subir após a infraestrutura de rede
#  12. Habilita os serviços para o boot
#
# Uso:
#   sudo bash tools/install_service.sh
#
# =============================================================================

set -euo pipefail

# ---- cores -------------------------------------------------------------------
_G="\e[92m"
_Y="\e[93m"
_R="\e[91m"
_C="\e[96m"
_B="\e[1m"
_RST="\e[0m"

info()   { echo -e "${_G}[INFO]${_RST}  $*"; }
warn()   { echo -e "${_Y}[WARN]${_RST}  $*"; }
error()  { echo -e "${_R}[ERRO]${_RST}  $*" >&2; }
titulo() { echo -e "\n${_B}${_C}$*${_RST}\n"; }
ok()     { echo -e "  ${_G}✓${_RST} $*"; }
fail()   { echo -e "  ${_R}✗${_RST} $*"; }

# ---- configurações -----------------------------------------------------------
SERVICE_NAME="tesseract-bridge"
WATCHDOG_SERVICE="${SERVICE_NAME}-watchdog"
WATCHDOG_TIMER="${SERVICE_NAME}-watchdog.timer"

# IMPORTANTE:
# Ajuste esta URL se o Flask do bridge estiver em outra porta/rota.
# O valor deve responder com HTTP 2xx quando o bridge estiver saudável.
BRIDGE_URL="${BRIDGE_URL:-http://127.0.0.1:8088/}"

# Tempo máximo para o watchdog considerar o bridge sem resposta.
WATCHDOG_TIMEOUT="${WATCHDOG_TIMEOUT:-5}"

# Intervalo entre verificações do watchdog.
WATCHDOG_INTERVAL="${WATCHDOG_INTERVAL:-30}"

# Tempo máximo que o launcher do kiosk espera o bridge.
KIOSK_MAX_WAIT="${KIOSK_MAX_WAIT:-120}"

# ---- verificar OS ------------------------------------------------------------
if [[ "$OSTYPE" != "linux"* ]]; then
    error "Este script requer Linux (systemd)."
    exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
    error "systemctl não encontrado. Este sistema precisa utilizar systemd."
    exit 1
fi

# ---- verificar sudo ----------------------------------------------------------
if [ "$EUID" -ne 0 ]; then
    error "Este script precisa ser executado com sudo:"
    echo "    sudo bash tools/install_service.sh"
    exit 1
fi

titulo "=== Tesseract Device Bridge — Instalação do Serviço ==="

# ---- detectar diretório do projeto -------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

info "Diretório do projeto: ${_C}$PROJECT_DIR${_RST}"

if [ ! -f "$PROJECT_DIR/run_bridge.py" ]; then
    error "run_bridge.py não encontrado em $PROJECT_DIR"
    error "Execute o script de DENTRO do repositório:"
    echo "    cd /caminho/para/Tesseract-Device-Bridge"
    echo "    sudo bash tools/install_service.sh"
    exit 1
fi
ok "run_bridge.py encontrado"

# ---- verificar devices.yml ---------------------------------------------------
if [ ! -f "$PROJECT_DIR/data/public/devices.yml" ]; then
    warn "data/public/devices.yml não encontrado."
    warn "O bridge poderá criá-lo/configurá-lo no primeiro boot, conforme sua aplicação."
else
    ok "devices.yml encontrado"
fi

# ---- detectar usuário --------------------------------------------------------
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

SERVICE_HOME="$(getent passwd "$SERVICE_USER" | cut -d: -f6)"
if [ -z "$SERVICE_HOME" ]; then
    SERVICE_HOME="$(eval echo "~$SERVICE_USER")"
fi

ok "Serviço vai rodar como: $SERVICE_USER (home: $SERVICE_HOME)"

# ---- detectar Python / venv --------------------------------------------------
titulo "=== Detectando Python / venv ==="

VENV_DIR=""
PYTHON_BIN=""
ACTIVATE_CMD=""

if [ -f "$PROJECT_DIR/.venv/bin/activate" ]; then
    VENV_DIR="$PROJECT_DIR/.venv"
    info "Venv detectada: ${_C}$VENV_DIR${_RST}"
elif [ -f "$PROJECT_DIR/venv/bin/activate" ]; then
    VENV_DIR="$PROJECT_DIR/venv"
    info "Venv detectada: ${_C}$VENV_DIR${_RST}"
fi

if [ -n "$VENV_DIR" ]; then
    PYTHON_BIN="$VENV_DIR/bin/python3"

    if [ ! -x "$PYTHON_BIN" ]; then
        error "A venv existe, mas o Python não é executável: $PYTHON_BIN"
        exit 1
    fi

    # O serviço fará source da venv antes de executar o Python.
    ACTIVATE_CMD="source '$VENV_DIR/bin/activate' && "
    ok "Venv será ativada SEMPRE antes de iniciar o bridge"
else
    warn "Nenhuma venv encontrada no projeto (.venv/ ou venv/)."
    warn "O serviço usará o Python global."
    warn "Recomendado criar uma venv antes de instalar o serviço."

    PYTHON_BIN="$(su -s /bin/bash "$SERVICE_USER" -c "command -v python3 2>/dev/null" || true)"
    PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"

    if [ -z "$PYTHON_BIN" ]; then
        error "Python não encontrado."
        echo "  Instale com: sudo apt install python3 python3-venv"
        exit 1
    fi
fi

PYTHON_VERSION="$("$PYTHON_BIN" --version 2>&1)"
ok "Python: $PYTHON_BIN ($PYTHON_VERSION)"

# ---- testar imports ----------------------------------------------------------
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

if [ -n "$VENV_DIR" ]; then
    # shellcheck source=/dev/null
    source "$VENV_DIR/bin/activate"
    PYTHON_BIN="$VENV_DIR/bin/python3"
    ok "Venv ativada para verificação de imports"
fi

check_import "flask"     "pip install flask"
check_import "paho.mqtt" "pip install paho-mqtt"
check_import "yaml"      "pip install PyYAML"
check_import "gpiozero"  "pip install gpiozero"

if [ $IMPORT_ERRORS -gt 0 ]; then
    echo ""
    error "$IMPORT_ERRORS dependência(s) ausente(s)."

    if [ -n "$VENV_DIR" ]; then
        echo "  Com a venv ativa:"
        echo "    source $VENV_DIR/bin/activate"
        echo "    pip install -r $PROJECT_DIR/requirements.txt"
    else
        echo "  Instale com:"
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

# Restaurar caminho absoluto da venv.
if [ -n "$VENV_DIR" ]; then
    PYTHON_BIN="$VENV_DIR/bin/python3"
fi

# ---- verificar curl ----------------------------------------------------------
if ! command -v curl >/dev/null 2>&1; then
    warn "curl não está instalado."
    echo "  O watchdog precisa de curl para testar o bridge."
    read -rp "  Instalar curl agora via apt? [S/n]: " INSTALL_CURL
    INSTALL_CURL="${INSTALL_CURL:-s}"

    if [[ "$INSTALL_CURL" =~ ^[SsYy]$ ]]; then
        apt-get update
        apt-get install -y curl
    else
        error "curl é necessário para o watchdog."
        exit 1
    fi
fi

ok "curl disponível"

# ---- configurar URL do bridge ------------------------------------------------
echo ""
echo -e "  URL usada para verificar se o bridge está saudável:"
echo -e "    ${_C}$BRIDGE_URL${_RST}"
read -rp "  Alterar URL? [s/N]: " CHANGE_URL
CHANGE_URL="${CHANGE_URL:-n}"

if [[ "$CHANGE_URL" =~ ^[SsYy]$ ]]; then
    read -rp "  URL do healthcheck: " INPUT_URL
    if [ -n "$INPUT_URL" ]; then
        BRIDGE_URL="$INPUT_URL"
    fi
fi

ok "Healthcheck: $BRIDGE_URL"

# ---- criar pasta de logs -----------------------------------------------------
LOG_DIR="/var/log/tesseract-bridge"

mkdir -p "$LOG_DIR"
chown "$SERVICE_USER:$SERVICE_USER" "$LOG_DIR"

ok "Pasta de log criada: $LOG_DIR"
info "Boot log disponível em: ${_C}$LOG_DIR/boot.log${_RST}"

# ---- criar diretório de ferramentas -----------------------------------------
TOOLS_DIR="$SERVICE_HOME/tools"
AUTOSTART_DIR="$SERVICE_HOME/.config/autostart"

mkdir -p "$TOOLS_DIR"
mkdir -p "$AUTOSTART_DIR"

chown "$SERVICE_USER:$SERVICE_USER" "$TOOLS_DIR" "$AUTOSTART_DIR"

# =============================================================================
# SERVIÇO PRINCIPAL
# =============================================================================

titulo "=== Gerando serviço principal ==="

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if [ -n "$ACTIVATE_CMD" ]; then
    EXEC_START="/bin/bash -lc '${ACTIVATE_CMD}cd \"$PROJECT_DIR\" && exec python3 run_bridge.py'"
    EXEC_DESCRIPTION="source venv + cd projeto + python3 run_bridge.py"
else
    EXEC_START="/bin/bash -lc 'cd \"$PROJECT_DIR\" && exec \"$PYTHON_BIN\" run_bridge.py'"
    EXEC_DESCRIPTION="cd projeto + Python absoluto"
fi

ok "ExecStart: $EXEC_DESCRIPTION"
ok "WorkingDirectory: $PROJECT_DIR"

cat > "$SERVICE_FILE" << SERVICE
[Unit]
Description=Tesseract Device Bridge
Documentation=https://github.com/ChristopherNicolasSMM/Tesseract-Device-Bridge

# O bridge depende da rede para MQTT/serviços externos.
# network-online.target é mais apropriado que apenas network.target.
After=network-online.target
Wants=network-online.target

# Faz o bridge ser iniciado na fase gráfica, depois da infraestrutura básica.
# O Chromium será iniciado separadamente pelo autostart do usuário.
After=graphical.target

[Service]
Type=simple

User=$SERVICE_USER
Group=$SERVICE_USER

WorkingDirectory=$PROJECT_DIR

Environment=FORCE_COLOR=1
Environment=PYTHONUNBUFFERED=1

# Executa o bash como processo intermediário apenas para ativar a venv.
# O exec substitui o shell pelo Python, deixando o PID do serviço limpo.
ExecStart=$EXEC_START

# Reinicia tanto em crash quanto em encerramento inesperado.
# Um "systemctl stop" manual continua parando normalmente.
Restart=always
RestartSec=5

# Evita uma tempestade de reinícios se houver um erro grave persistente.
StartLimitIntervalSec=60
StartLimitBurst=5

# Se o Python não responder ao SIGTERM, o systemd força o encerramento.
TimeoutStopSec=15

StandardOutput=journal
StandardError=journal

[Install]
# O serviço entra na sequência normal de boot e possui dependência explícita
# de network-online.target. A interface gráfica/kiosk não depende de um
# autostart systemd de usuário.
WantedBy=graphical.target
SERVICE

chmod 644 "$SERVICE_FILE"

ok "Serviço criado: $SERVICE_FILE"

# =============================================================================
# WATCHDOG
# =============================================================================

titulo "=== Gerando watchdog do bridge ==="

WATCHDOG_FILE="/etc/systemd/system/${WATCHDOG_SERVICE}.service"
WATCHDOG_TIMER_FILE="/etc/systemd/system/${WATCHDOG_TIMER}"

cat > "$WATCHDOG_FILE" << WATCHDOG
[Unit]
Description=Healthcheck do Tesseract Device Bridge
After=$SERVICE_NAME.service
Requires=$SERVICE_NAME.service

[Service]
Type=oneshot

# Se o endpoint não responder em WATCHDOG_TIMEOUT segundos, reinicia o bridge.
# --fail exige HTTP 4xx/5xx como falha.
# --silent/--show-error evita poluir o journal.
ExecStart=/bin/bash -c 'if ! curl --fail --silent --show-error --max-time $WATCHDOG_TIMEOUT "$BRIDGE_URL" >/dev/null; then echo "WATCHDOG: bridge sem resposta em $BRIDGE_URL — reiniciando serviço"; systemctl restart $SERVICE_NAME.service; else echo "WATCHDOG: bridge OK"; fi'
WATCHDOG

cat > "$WATCHDOG_TIMER_FILE" << WATCHDOG_TIMER
[Unit]
Description=Executa healthcheck periódico do Tesseract Device Bridge

[Timer]
OnBootSec=60s
OnUnitActiveSec=${WATCHDOG_INTERVAL}s
Unit=$WATCHDOG_SERVICE.service
Persistent=true

[Install]
WantedBy=timers.target
WATCHDOG_TIMER

chmod 644 "$WATCHDOG_FILE" "$WATCHDOG_TIMER_FILE"

ok "Watchdog criado"
ok "Intervalo: ${WATCHDOG_INTERVAL}s"
ok "Timeout: ${WATCHDOG_TIMEOUT}s"

# =============================================================================
# LAUNCHER DO CHROMIUM KIOSK
# =============================================================================

titulo "=== Gerando launcher do Chromium kiosk ==="

KIOSK_SCRIPT="$TOOLS_DIR/tesseract-kiosk.sh"

cat > "$KIOSK_SCRIPT" << KIOSK
#!/usr/bin/env bash
# =============================================================================
# tesseract-kiosk.sh
# Aguarda o Tesseract Device Bridge e então abre o Chromium em kiosk.
# =============================================================================

set -u

BRIDGE_URL="$BRIDGE_URL"
MAX_WAIT="$KIOSK_MAX_WAIT"

# Raspberry Pi pode possuir chromium ou chromium-browser dependendo da versão.
if command -v chromium-browser >/dev/null 2>&1; then
    CHROMIUM_BIN="chromium-browser"
elif command -v chromium >/dev/null 2>&1; then
    CHROMIUM_BIN="chromium"
else
    echo "[ERRO] Chromium não encontrado." >&2
    exit 1
fi

echo "[KIOSK] Aguardando Tesseract Device Bridge em: \$BRIDGE_URL"

WAITED=0

while ! curl --fail --silent --max-time 2 "\$BRIDGE_URL" >/dev/null 2>&1; do
    sleep 2
    WAITED=\$((WAITED + 2))

    if [ "\$WAITED" -ge "\$MAX_WAIT" ]; then
        echo "[KIOSK] Bridge não respondeu em \${MAX_WAIT}s."
        echo "[KIOSK] Abrindo Chromium mesmo assim."
        break
    fi
done

if [ "\$WAITED" -lt "\$MAX_WAIT" ]; then
    echo "[KIOSK] Bridge respondeu. Abrindo Chromium."
fi

# Pequena margem para garantir que o desktop terminou de inicializar.
sleep 2

exec "\$CHROMIUM_BIN" \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-features=TranslateUI \
    --autoplay-policy=no-user-gesture-required \
    --check-for-update-interval=31536000 \
    "\$BRIDGE_URL"
KIOSK

chmod +x "$KIOSK_SCRIPT"
chown "$SERVICE_USER:$SERVICE_USER" "$KIOSK_SCRIPT"

ok "Launcher kiosk criado: $KIOSK_SCRIPT"

# =============================================================================
# AUTOSTART DOS LOGS
# =============================================================================

titulo "=== Configurando autostart do desktop ==="

AUTOSTART_LOGS="$AUTOSTART_DIR/tesseract-bridge-logs.desktop"

read -rp "  Criar terminal de logs ao iniciar o desktop? [S/n]: " CREATE_LOG_AUTOSTART
CREATE_LOG_AUTOSTART="${CREATE_LOG_AUTOSTART:-s}"

if [[ "$CREATE_LOG_AUTOSTART" =~ ^[SsYy]$ ]]; then

    cat > "$AUTOSTART_LOGS" << DESKTOP
[Desktop Entry]
Type=Application
Name=Tesseract Bridge — Logs
Comment=Abre o terminal de logs do Tesseract Device Bridge
Exec=bash -c 'sleep 5 && lxterminal --title="Tesseract Bridge — Logs" -e "bash -c \"journalctl -fu tesseract-bridge --output=cat --no-pager; exec bash\""'
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
DESKTOP

    chown "$SERVICE_USER:$SERVICE_USER" "$AUTOSTART_LOGS"
    ok "Autostart de logs criado: $AUTOSTART_LOGS"
fi

# =============================================================================
# AUTOSTART DO KIOSK
# =============================================================================

AUTOSTART_KIOSK="$AUTOSTART_DIR/tesseract-kiosk.desktop"

read -rp "  Abrir Chromium automaticamente em modo kiosk? [S/n]: " CREATE_KIOSK_AUTOSTART
CREATE_KIOSK_AUTOSTART="${CREATE_KIOSK_AUTOSTART:-s}"

if [[ "$CREATE_KIOSK_AUTOSTART" =~ ^[SsYy]$ ]]; then

    cat > "$AUTOSTART_KIOSK" << DESKTOP
[Desktop Entry]
Type=Application
Name=Tesseract Device Bridge — Kiosk
Comment=Abre o painel do Tesseract após o bridge responder
Exec=$KIOSK_SCRIPT
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=5
DESKTOP

    chown "$SERVICE_USER:$SERVICE_USER" "$AUTOSTART_KIOSK"
    ok "Autostart kiosk criado: $AUTOSTART_KIOSK"
fi

# =============================================================================
# HABILITAR SERVIÇOS
# =============================================================================

titulo "=== Habilitando serviços ==="

systemctl daemon-reload

systemctl enable "$SERVICE_NAME.service"
systemctl enable "$WATCHDOG_TIMER"

ok "Bridge habilitado para boot"
ok "Watchdog habilitado para boot"

# =============================================================================
# VALIDAR CONFIGURAÇÃO SYSTEMD
# =============================================================================

titulo "=== Validando configuração systemd ==="

systemd-analyze verify "$SERVICE_FILE" "$WATCHDOG_FILE" "$WATCHDOG_TIMER_FILE"

ok "Arquivos systemd válidos"

# =============================================================================
# INICIAR AGORA
# =============================================================================

echo ""
read -rp "  Iniciar o bridge agora? [S/n]: " START_NOW
START_NOW="${START_NOW:-s}"

if [[ "$START_NOW" =~ ^[SsYy]$ ]]; then

    systemctl restart "$SERVICE_NAME.service"

    # O restart pode levar alguns segundos para conectar MQTT/Flask.
    sleep 3

    if systemctl is-active --quiet "$SERVICE_NAME.service"; then
        ok "Bridge iniciado com sucesso!"
    else
        warn "Bridge não está ativo."
        echo ""
        echo "  Diagnóstico:"
        echo "    sudo systemctl status $SERVICE_NAME.service"
        echo "    sudo journalctl -u $SERVICE_NAME.service -n 80 --no-pager"
        echo "    cat $LOG_DIR/boot.log"
        echo ""

        systemctl status "$SERVICE_NAME.service" --no-pager -n 30 || true
    fi

    # Ativa o watchdog imediatamente.
    systemctl start "$WATCHDOG_TIMER"

    if systemctl is-active --quiet "$WATCHDOG_TIMER"; then
        ok "Watchdog ativo"
    else
        warn "Watchdog não ficou ativo."
    fi
fi

# =============================================================================
# RESUMO
# =============================================================================

titulo "=== Instalação concluída ==="

echo -e "  Serviço:             ${_C}$SERVICE_NAME${_RST}"
echo -e "  Usuário:             ${_C}$SERVICE_USER${_RST}"
echo -e "  Projeto:             ${_C}$PROJECT_DIR${_RST}"
echo -e "  Python/venv:         ${_C}${VENV_DIR:-python3 global}${_RST}"
echo -e "  Healthcheck:         ${_C}$BRIDGE_URL${_RST}"
echo -e "  Watchdog:            ${_C}a cada ${WATCHDOG_INTERVAL}s${_RST}"
echo -e "  Boot log:            ${_C}$LOG_DIR/boot.log${_RST}"
echo -e "  Kiosk launcher:      ${_C}$KIOSK_SCRIPT${_RST}"
echo ""

echo -e "  ${_B}Fluxo no boot:${_RST}"
echo "    1. Linux inicia"
echo "    2. network-online.target fica disponível"
echo "    3. tesseract-bridge inicia"
echo "    4. venv é ativada antes do Python"
echo "    5. Bridge permanece rodando com Restart=always"
echo "    6. Watchdog verifica o bridge periodicamente"
echo "    7. LXDE inicia"
echo "    8. Chromium espera o bridge responder"
echo "    9. Chromium abre em modo kiosk"
echo ""

echo -e "  ${_B}Comandos úteis:${_RST}"
echo -e "    ${_Y}sudo systemctl status $SERVICE_NAME${_RST}"
echo -e "    ${_Y}sudo journalctl -u $SERVICE_NAME -f${_RST}"
echo -e "    ${_Y}sudo systemctl restart $SERVICE_NAME${_RST}"
echo -e "    ${_Y}sudo systemctl stop $SERVICE_NAME${_RST}"
echo -e "    ${_Y}sudo systemctl status $WATCHDOG_TIMER${_RST}"
echo -e "    ${_Y}sudo journalctl -u $WATCHDOG_SERVICE -n 50 --no-pager${_RST}"
echo -e "    ${_Y}cat $LOG_DIR/boot.log${_RST}"
echo ""

echo -e "  ${_B}Arquivos instalados:${_RST}"
echo "    $SERVICE_FILE"
echo "    $WATCHDOG_FILE"
echo "    $WATCHDOG_TIMER_FILE"
echo "    $KIOSK_SCRIPT"
echo "    $AUTOSTART_KIOSK"
echo ""

echo -e "  ${_B}Para desinstalar:${_RST}"
echo -e "    ${_Y}sudo bash tools/uninstall_service.sh${_RST}"
echo ""
