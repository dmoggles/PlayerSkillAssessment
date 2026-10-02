#!/usr/bin/env bash
set -euo pipefail

# Run from the development deployment directory, after its current API image is deployed.
if [[ ! -f .env.dev || ! -f compose.yaml || ! -f compose.dev.yaml ]]; then
  echo 'Run this from the development deployment directory containing .env.dev and both Compose files.' >&2
  exit 1
fi
if [[ ! -t 0 || ! -t 1 ]]; then
  echo 'An interactive terminal is required so generated passwords do not enter CI logs.' >&2
  exit 1
fi

echo 'This will add synthetic data to the DEVELOPMENT database.'
echo 'It will rotate the two demo passwords and revoke their existing sessions.'
read -r -p 'Type SEED DEV to continue: ' confirmation
if [[ "$confirmation" != 'SEED DEV' ]]; then
  echo 'Cancelled.'
  exit 1
fi

docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml run --rm --no-deps -T api python -m app.seed_dev
