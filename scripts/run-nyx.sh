#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NYX_HOST="${NYX_HOST:-127.0.0.1}"
NYX_PORT="${NYX_PORT:-8765}"

cd "$ROOT_DIR"

if [[ ! -x .venv/bin/python ]]; then
  echo "Missing virtualenv at $ROOT_DIR/.venv. Run the local deploy/bootstrap steps first." >&2
  exit 1
fi

source .venv/bin/activate

exec uvicorn server:app --host "$NYX_HOST" --port "$NYX_PORT"
