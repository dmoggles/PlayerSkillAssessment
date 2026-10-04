#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if docker compose version >/dev/null 2>&1; then
  compose=(docker compose)
else
  compose=(docker-compose)
fi
# Version shown in the app: nearest release tag plus commits since, or the short commit.
APP_VERSION="$(git describe --tags --always --dirty 2>/dev/null || echo local)"
export APP_VERSION
"${compose[@]}" -f compose.yaml -f compose.local.yaml --profile local build api web
"${compose[@]}" -f compose.yaml -f compose.local.yaml --profile local up -d db mailpit
"${compose[@]}" -f compose.yaml -f compose.local.yaml --profile local run --rm migrate
"${compose[@]}" -f compose.yaml -f compose.local.yaml --profile local up -d api web
echo "App: http://localhost:8080  Email inbox: http://localhost:8025"
