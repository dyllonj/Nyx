#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLIENT_DIR="$ROOT_DIR/apps/nyx-client"
NODE_BIN_DIR="$ROOT_DIR/.runtime/node/bin"

if [[ -d "$NODE_BIN_DIR" ]]; then
  export PATH="$NODE_BIN_DIR:$PATH"
fi

cd "$CLIENT_DIR"

npm ci
EXPO_PUBLIC_API_BASE_URL= npx expo export --platform web
