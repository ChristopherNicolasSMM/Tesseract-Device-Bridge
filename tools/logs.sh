#!/usr/bin/env bash
# =============================================================================
# logs.sh — Exibe os logs do Tesseract Device Bridge ao vivo
# =============================================================================
#
# Uso:
#   bash tools/logs.sh           # logs ao vivo (CTRL+C para parar)
#   bash tools/logs.sh --all     # mostra logs desde o início desta sessão
#   bash tools/logs.sh --boot    # mostra logs desde o último boot
#
# Como funciona:
#   Usa journalctl com --output=cat para passar os códigos ANSI gerados
#   pelo ColoredFormatter do bridge (FORCE_COLOR=1 no serviço), mostrando
#   as cores exatamente como no terminal interativo.
#
# Pré-requisito:
#   O serviço precisa estar instalado e rodando.
#   Instalar com: sudo bash tools/install_service.sh
# =============================================================================

SERVICE_NAME="tesseract-bridge"

# Verificar se o serviço existe
if ! systemctl list-units --full --all 2>/dev/null | grep -q "$SERVICE_NAME"; then
    echo ""
    echo "  ⚠️  Serviço '$SERVICE_NAME' não encontrado."
    echo "     Instale primeiro: sudo bash tools/install_service.sh"
    echo ""
    exit 1
fi

# Cabeçalho
echo ""
echo "  ┌─────────────────────────────────────────────────────┐"
echo "  │  Tesseract Device Bridge — Logs ao vivo              │"
echo "  │  CTRL+C para parar                                   │"
echo "  └─────────────────────────────────────────────────────┘"
echo ""

# Status rápido do serviço antes de mostrar os logs
STATUS="$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || echo "desconhecido")"
if [ "$STATUS" = "active" ]; then
    echo "  ● Serviço: ATIVO ✓"
elif [ "$STATUS" = "inactive" ]; then
    echo "  ○ Serviço: INATIVO (não está rodando)"
elif [ "$STATUS" = "failed" ]; then
    echo "  ✗ Serviço: FALHOU — use 'sudo systemctl status $SERVICE_NAME' para detalhes"
else
    echo "  ? Serviço: $STATUS"
fi
echo ""

# Opções de filtro temporal
if [[ "${1:-}" == "--all" ]]; then
    # Todos os logs desta sessão do serviço (sem --since)
    EXTRA_ARGS="--no-pager"
elif [[ "${1:-}" == "--boot" ]]; then
    # Desde o último boot
    EXTRA_ARGS="--since=@$(who -b 2>/dev/null | awk '{print $3" "$4}' | xargs -I{} date -d "{}" +%s 2>/dev/null || echo "0")"
    EXTRA_ARGS="--boot=0 --no-pager"
else
    # Padrão: só ao vivo (últimas 50 linhas + follow)
    EXTRA_ARGS="-n 50"
fi

# --output=cat: passa os códigos ANSI do bridge diretamente, sem
# adicionar prefixos do journald (timestamp, hostname, etc.) — o
# ColoredFormatter já formata tudo o que precisamos.
exec journalctl -fu "$SERVICE_NAME" --output=cat $EXTRA_ARGS
