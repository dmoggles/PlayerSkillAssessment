#!/usr/bin/env bash
# Encrypted PostgreSQL backups for one deployment (production, or development for testing).
#
#   bash deploy/backup.sh nightly       the timer's run: kept 30 days, plus one a month kept a year
#   bash deploy/backup.sh pre-deploy    taken by the production deploy before migrations: last 10 kept
#
# Run from the deployment directory (the one holding .env.prod or .env.dev). Settings come from .backup.env there
# (see deploy/backup.env.example). The dump is encrypted with age before it touches disk, so no copy, local or
# remote, can be read without the private key, which stays off this server. Each backup goes to:
#   - BACKUP_DIR on this server (pruned here),
#   - an S3-compatible bucket through rclone (retention set on the bucket; the key needs no delete rights),
#   - a second server over rsync, write-only (pruned by that server: deploy/setup_backup_mirror.sh).
# At least one of the two off-server copies must be configured. A health-check URL, if set, is pinged on success
# and on failure, so a missed or failed backup raises an alert.
set -euo pipefail

kind=${1:-}
[[ $kind == nightly || $kind == pre-deploy || $kind == pre-restore ]] || { echo "Usage: bash deploy/backup.sh nightly|pre-deploy" >&2; exit 2; }

cd "$(dirname "$0")/.."
[[ -f .backup.env ]] || { echo "Missing .backup.env in $(pwd); copy deploy/backup.env.example and fill it in." >&2; exit 1; }
set -a; . ./.backup.env; set +a

if [[ -f .env.prod ]]; then compose=(docker compose --env-file .env.prod -f compose.yaml -f compose.prod.yaml); stack=prod
elif [[ -f .env.dev ]]; then compose=(docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml); stack=dev
else echo "No .env.prod or .env.dev in $(pwd)." >&2; exit 1; fi

: "${BACKUP_AGE_RECIPIENT:?Set BACKUP_AGE_RECIPIENT in .backup.env to the age public key}"
[[ -n ${BACKUP_REMOTE:-} || -n ${BACKUP_MIRROR:-} ]] || { echo "Set BACKUP_REMOTE and/or BACKUP_MIRROR in .backup.env: a backup must leave this server." >&2; exit 1; }
backup_dir=${BACKUP_DIR:-$(pwd)/backups}
keep_daily=${BACKUP_KEEP_DAILY:-30}; keep_monthly=${BACKUP_KEEP_MONTHLY:-12}; keep_predeploy=${BACKUP_KEEP_PREDEPLOY:-10}

ping() {  # ping the health check: "" on success, "/fail" on failure
  [[ -n ${BACKUP_HEALTHCHECK_URL:-} ]] || return 0
  curl -fsS -m 10 --retry 3 --data-raw "$2" "${BACKUP_HEALTHCHECK_URL%/}$1" >/dev/null || echo "Health check ping failed." >&2
}
only_nightly_pings() { [[ $kind == nightly ]]; }
on_error() {
  local message="$kind backup of $stack failed at line $1"
  echo "$message" >&2
  only_nightly_pings && ping /fail "$message"
  rm -f "${partial:-}"
}
trap 'on_error $LINENO' ERR

for tool in age docker; do command -v $tool >/dev/null || { echo "$tool is not installed." >&2; exit 1; }; done
[[ -z ${BACKUP_REMOTE:-} ]] || command -v rclone >/dev/null || { echo "rclone is not installed." >&2; exit 1; }
[[ -z ${BACKUP_MIRROR:-} ]] || command -v rsync >/dev/null || { echo "rsync is not installed." >&2; exit 1; }

stamp=$(date -u +%Y%m%dT%H%M%SZ)
name="tapline-idp-$stack-$stamp${RELEASE_TAG:+-$RELEASE_TAG}.dump.age"
folder=$([[ $kind == nightly ]] && echo daily || echo "$kind")
mkdir -p "$backup_dir/$folder"
chmod 700 "$backup_dir"
partial="$backup_dir/$folder/.$name.partial"

# Dump and encrypt in one stream; pipefail makes a failed pg_dump fail the whole line.
"${compose[@]}" exec -T db pg_dump -U assessment_owner -d assessment -Fc | age -r "$BACKUP_AGE_RECIPIENT" > "$partial"
[[ -s $partial ]] || { echo "The backup came out empty." >&2; false; }
mv "$partial" "$backup_dir/$folder/$name"
files=("$folder/$name")
# The first nightly backup of each month is also kept as a monthly one.
if [[ $kind == nightly ]] && ! ls "$backup_dir/monthly/tapline-idp-$stack-${stamp:0:6}"* >/dev/null 2>&1; then
  mkdir -p "$backup_dir/monthly"
  cp "$backup_dir/$folder/$name" "$backup_dir/monthly/$name"
  files+=("monthly/$name")
fi
size=$(du -h "$backup_dir/$folder/$name" | cut -f1)

prune() {  # keep the newest $2 files in folder $1
  [[ -d $backup_dir/$1 ]] || return 0
  ls -1t "$backup_dir/$1"/*.dump.age 2>/dev/null | tail -n +"$(($2 + 1))" | xargs -r rm -f
}
prune daily "$keep_daily"; prune monthly "$keep_monthly"; prune pre-deploy "$keep_predeploy"; prune pre-restore "$keep_predeploy"

copies="this server"
if [[ -n ${BACKUP_REMOTE:-} ]]; then
  for file in "${files[@]}"; do rclone copyto -q --s3-no-check-bucket "$backup_dir/$file" "${BACKUP_REMOTE%/}/$file"; done
  copies+=", ${BACKUP_REMOTE%%:*}"
fi
if [[ -n ${BACKUP_MIRROR:-} ]]; then
  # The mirror's host key is remembered on first contact, and a changed one is refused.
  ssh_command="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new${BACKUP_MIRROR_SSH_KEY:+ -i $BACKUP_MIRROR_SSH_KEY}"
  # Relative paths, so the mirror's folders match these; the mirror refuses deletes and reads.
  (cd "$backup_dir" && rsync -a --relative -e "$ssh_command" "${files[@]}" "${BACKUP_MIRROR%/}/")
  copies+=", ${BACKUP_MIRROR%%:*}"
fi

message="$kind backup of $stack: $name ($size), copied to $copies"
echo "$message"
only_nightly_pings && ping "" "$message"
exit 0
