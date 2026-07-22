#!/usr/bin/env bash
# Start the Commutr AI Agent HTTP server in the background.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

VENV="${DIR}/.venv/bin/activate"
LOG="${DIR}/server.log"
PIDFILE="${DIR}/.server.pid"
PORT="${COMMUTR_AGENT_PORT:-8765}"
HOST="${COMMUTR_AGENT_HOST:-127.0.0.1}"

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Server already running (pid $(cat "$PIDFILE"))."
  exit 0
fi

# shellcheck disable=SC1091
source "$VENV"

echo "Starting Commutr AI Agent server on http://${HOST}:${PORT} ..."
nohup python server.py --host "$HOST" --port "$PORT" > "$LOG" 2>&1 &
echo $! > "$PIDFILE"

# Wait briefly for the port to come up.
for _ in $(seq 1 30); do
  if curl -sf "http://${HOST}:${PORT}/health" >/dev/null 2>&1; then
    echo "Server is up: http://${HOST}:${PORT}/health"
    exit 0
  fi
  sleep 0.5
done

echo "Server started but /health not ready yet. Check ${LOG}."
