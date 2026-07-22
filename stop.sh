#!/usr/bin/env bash
# Stop the background Commutr AI Agent HTTP server.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDFILE="${DIR}/.server.pid"

if [[ ! -f "$PIDFILE" ]]; then
  echo "No pid file found. Server may not be running."
  exit 0
fi

PID="$(cat "$PIDFILE")"
if kill -0 "$PID" 2>/dev/null; then
  echo "Stopping server (pid ${PID}) ..."
  kill "$PID"
  # Wait for graceful shutdown.
  for _ in $(seq 1 20); do
    kill -0 "$PID" 2>/dev/null || break
    sleep 0.5
  done
  if kill -0 "$PID" 2>/dev/null; then
    echo "Force killing ..."
    kill -9 "$PID" || true
  fi
  echo "Server stopped."
else
  echo "Process ${PID} not running (stale pid file)."
fi

rm -f "$PIDFILE"
