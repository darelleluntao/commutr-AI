#!/usr/bin/env bash
# Interactive chat client for the Commutr AI Agent server.
# Talks to the running server (start.sh) via the /ask endpoint.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDFILE="${DIR}/.server.pid"
PORT="${COMMUTR_AGENT_PORT:-8765}"
HOST="${COMMUTR_AGENT_HOST:-127.0.0.1}"
BASE="http://${HOST}:${PORT}"

# Auto-start the server if it isn't running.
if [[ ! -f "$PIDFILE" ]] || ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Server not running — starting it..."
  "${DIR}/start.sh"
fi

echo "Commutr AI Agent — interactive (server at ${BASE})"
echo "Type your question, or 'exit' / Ctrl-C to quit."
echo

while true; do
  printf "> "
  read -r QUESTION || break
  LOWER=$(printf '%s' "$QUESTION" | tr '[:upper:]' '[:lower:]')
  if [[ "$LOWER" == "exit" || "$LOWER" == "quit" || "$LOWER" == "q" ]]; then
    break
  fi
  if [[ -z "${QUESTION// /}" ]]; then
    continue
  fi

  RESP=$(curl -s -X POST "${BASE}/ask" \
    -H "Content-Type: application/json" \
    -d "$(printf '{"question": %s}' "$(python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "$QUESTION")")")
  echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('answer',''), f\"\n[{d.get('elapsed_ms',0)} ms]\")" 2>/dev/null || echo "$RESP"
  echo
done
