#!/data/data/com.termux/files/usr/bin/bash
# Entry point per ~/.termux/boot/ (Termux:Boot). Avvia il supervisor in background.
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
"$SCRIPT_DIR/start-agent.sh" >/dev/null 2>&1 &
disown
