#!/data/data/com.termux/files/usr/bin/bash
# Avvio con wake-lock e loop di riavvio (C-12, decisione D1).
# Uso: start-agent.sh   (APP_DIR e CONFIG sovrascrivibili da ambiente)
set -u

APP_DIR="${APP_DIR:-$HOME/agente-personale}"
CONFIG="${CONFIG:-$HOME/.config/agente/config.toml}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
LOG_DIR="${LOG_DIR:-$HOME/.local/share/agente/logs}"
RESTART_BACKOFF=5
RESTART_BACKOFF_MAX=300

export PYTHONPATH="$APP_DIR/src:$APP_DIR/.deps${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

mkdir -p "$LOG_DIR"
chmod 700 "$LOG_DIR" 2>/dev/null || true

termux-wake-lock 2>/dev/null || true
trap 'termux-wake-unlock 2>/dev/null || true' EXIT

while true; do
    "$PYTHON_BIN" -m agente --config "$CONFIG"
    code=$?
    echo "[supervisor] agente terminato con codice $code, riavvio tra ${RESTART_BACKOFF}s" \
        | tee -a "$LOG_DIR/supervisor.log" >&2
    sleep "$RESTART_BACKOFF"
    RESTART_BACKOFF=$((RESTART_BACKOFF * 2))
    if [ "$RESTART_BACKOFF" -gt "$RESTART_BACKOFF_MAX" ]; then
        RESTART_BACKOFF=$RESTART_BACKOFF_MAX
    fi
done
