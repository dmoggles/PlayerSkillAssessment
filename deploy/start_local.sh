#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if docker compose version >/dev/null 2>&1; then
  compose=(docker compose)
else
  compose=(docker-compose)
fi
"${compose[@]}" -f compose.yaml -f compose.local.yaml --profile local build api web
"${compose[@]}" -f compose.yaml -f compose.local.yaml --profile local up -d db mailpit
"${compose[@]}" -f compose.yaml -f compose.local.yaml --profile local run --rm migrate
"${compose[@]}" -f compose.yaml -f compose.local.yaml --profile local up -d api web
echo "App: http://localhost:8080  Email inbox: http://localhost:8025"
