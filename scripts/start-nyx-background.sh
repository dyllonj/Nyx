#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT_DIR/.runtime/nyx-background.pid"
LOG_DIR="$ROOT_DIR/.runtime/logs"
LOG_FILE="$LOG_DIR/nyx.log"
RUNNER="$ROOT_DIR/scripts/run-nyx-dual.sh"
ENV_FILE="${NYX_ENV_FILE:-/home/deck/.config/nyx/nyx.env}"

mkdir -p "$LOG_DIR"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

if [[ -f "$PID_FILE" ]]; then
  existing_pid="$(cat "$PID_FILE")"
  if kill -0 "$existing_pid" 2>/dev/null; then
    exit 0
  fi
  rm -f "$PID_FILE"
fi

nohup "$RUNNER" >>"$LOG_FILE" 2>&1 &
echo "$!" > "$PID_FILE"
