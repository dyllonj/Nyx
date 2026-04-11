#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT_DIR/.runtime/nyx-background.pid"

if [[ ! -f "$PID_FILE" ]]; then
  exit 0
fi

pid="$(cat "$PID_FILE")"
kill "$pid" 2>/dev/null || true
rm -f "$PID_FILE"
