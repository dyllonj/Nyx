#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_HOST="${NYX_LOCAL_HOST:-127.0.0.1}"
NYX_PORT="${NYX_PORT:-8765}"
TAILSCALE_HOST="${NYX_TAILSCALE_HOST:-auto}"

cd "$ROOT_DIR"

if [[ ! -x .venv/bin/python ]]; then
  echo "Missing virtualenv at $ROOT_DIR/.venv. Run the local deploy/bootstrap steps first." >&2
  exit 1
fi

source .venv/bin/activate

resolve_tailscale_host() {
  .venv/bin/python - <<'PY'
import fcntl
import socket
import struct

iface = b"tailscale0"
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    addr = fcntl.ioctl(s.fileno(), 0x8915, struct.pack("256s", iface[:15]))[20:24]
    print(socket.inet_ntoa(addr))
except OSError:
    pass
finally:
    s.close()
PY
}

PIDS=()

cleanup() {
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait || true
}

trap cleanup EXIT INT TERM

start_listener() {
  local host="$1"
  echo "Starting Nyx on http://$host:$NYX_PORT"
  uvicorn server:app --host "$host" --port "$NYX_PORT" &
  PIDS+=("$!")
}

start_listener "$LOCAL_HOST"

if [[ "$TAILSCALE_HOST" == "auto" ]]; then
  TAILSCALE_HOST="$(resolve_tailscale_host)"
fi

if [[ -n "$TAILSCALE_HOST" && "$TAILSCALE_HOST" != "$LOCAL_HOST" ]]; then
  start_listener "$TAILSCALE_HOST"
fi

wait -n "${PIDS[@]}"
