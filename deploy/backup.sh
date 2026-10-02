#!/usr/bin/env bash
set -euo pipefail

: "${BACKUP_S3_URI:?Set BACKUP_S3_URI to an off-host s3:// bucket/prefix}"
: "${BACKUP_AGE_RECIPIENT:?Set BACKUP_AGE_RECIPIENT to an age public key}"

cd "$(dirname "$0")/.."
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
docker compose --env-file .env.prod -f compose.yaml -f compose.prod.yaml exec -T db pg_dump -U assessment_owner -d assessment -Fc \
  | age -r "$BACKUP_AGE_RECIPIENT" \
  | aws s3 cp - "${BACKUP_S3_URI%/}/assessment-${stamp}.dump.age"
