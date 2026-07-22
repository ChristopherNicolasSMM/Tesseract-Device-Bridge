#!/usr/bin/env bash
# =============================================================================
# logs.sh — Exibe os logs do Tesseract Device Bridge ao vivo
# =============================================================================
#
# Uso:
#   bash tools/logs.sh              # logs ao vivo (CTRL+C para parar)
#   bash tools/logs.sh --all        # logs desde o inicio desta sessao
#   bash tools/logs.sh --boot       # logs desde o ultimo boot
#   bash tools/logs.sh --boot-log   # log de inicializacao (diagnostico de falha)
#
# O --boot-log mostra /var/log/tesseract-bridge/boot.log,
# gravado ANTES do logging Python subir — util quando o servico
# falha no boot e o journal nao mostra o motivo claro.
# =============================================================================

SERVICE_NAME="tesseract-bridge"
BOOT_LOG_FILE="/var/log/tesseract-bridge/boot.log"
BOOT_LOG_FALLBACK="./logs/boot.log"

# ---- opcao --boot-log -------------------------------------------------------
if [[ "${1:-}" == "--boot-log" ]]; then
    echo ""
    echo "  Tesseract Bridge - Boot Log (diagnostico de falha)"
    echo "  ======================================================"
    echo ""

    if [ -f "$BOOT_LOG_FILE" ]; then
        echo "  Arquivo: $BOOT_LOG_FILE"
        echo ""
        cat "$BOOT_LOG_FILE"
    elif [ -f "$BOOT_LOG_FALLBACK" ]; then
        echo "  Arquivo: $BOOT_LOG_FALLBACK"
        echo ""
        cat "$BOOT_LOG_FALLBACK"
    else
        echo "  Boot log nao encontrado."
        echo "  Caminhos verificados:"
        echo "    $BOOT_LOG_FILE"
        echo "    $BOOT_LOG_FALLBACK"
        echo ""
        echo "  O boot.log so existe se o bridge ja tiver sido iniciado"
        echo "  pelo menos uma vez (manualmente ou como servico)."
    fi
    echo ""
    exit 0
fi

# ---- verificar se o servico existe -----------------------------------------
if ! systemctl list-units --full --all 2>/dev/null | grep -q "$SERVICE_NAME"; then
    echo ""
    echo "  Servico '$SERVICE_NAME' nao encontrado."
    echo "  Instale primeiro: sudo bash tools/install_service.sh"
    echo ""
    exit 1
fi

echo ""
echo "  Tesseract Device Bridge - Logs ao vivo (CTRL+C para parar)"
echo "  ============================================================"
echo ""

STATUS="$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || echo "desconhecido")"
if [ "$STATUS" = "active" ]; then
    echo "  Servico: ATIVO"
elif [ "$STATUS" = "inactive" ]; then
    echo "  Servico: INATIVO"
    echo ""
    echo "  Para ver por que nao iniciou:"
    echo "    bash tools/logs.sh --boot-log"
    echo "    sudo journalctl -u $SERVICE_NAME -n 30"
elif [ "$STATUS" = "failed" ]; then
    echo "  Servico: FALHOU"
    echo ""
    echo "  Diagnostico:"
    echo "    bash tools/logs.sh --boot-log"
    echo "    sudo journalctl -u $SERVICE_NAME -n 30"
else
    echo "  Servico: $STATUS"
fi
echo ""

# Mostrar boot log resumido se o servico nao esta ativo
if [ "$STATUS" != "active" ] && [ -f "$BOOT_LOG_FILE" ]; then
    echo "  Ultimas linhas do boot log:"
    tail -10 "$BOOT_LOG_FILE" | sed 's/^/    /'
    echo ""
fi

# Opcoes de filtro temporal
if [[ "${1:-}" == "--all" ]]; then
    EXTRA_ARGS="--no-pager"
elif [[ "${1:-}" == "--boot" ]]; then
    EXTRA_ARGS="--boot=0 --no-pager"
else
    EXTRA_ARGS="-n 50"
fi

exec journalctl -fu "$SERVICE_NAME" --output=cat $EXTRA_ARGS
