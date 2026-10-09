#!/usr/bin/env bash
# Restore an encrypted backup made by deploy/backup.sh.
#
#   bash deploy/restore.sh check   KEY_FILE BACKUP.dump.age   restore into a throwaway database and report what is in it
#   bash deploy/restore.sh replace KEY_FILE BACKUP.dump.age   replace this deployment's database with the backup
#
# KEY_FILE is the age private key; bring it to the server only for the restore and delete it afterwards.
# `check` needs only Docker and age, so it also runs on your own computer or the other VPS. Practise it every
# few months: a backup that has never been restored is not known to work. To fetch a backup from the bucket:
#   rclone copy offsite:BUCKET/daily/NAME.dump.age .     (with the RCLONE_CONFIG_OFFSITE_* settings exported)
# `replace` runs in the deployment directory. It first takes a backup of the current database (kept in
# pre-restore/), stops the app, restores, re-applies the app user's access, and starts the app again.
set -euo pipefail

mode=${1:-}; key=${2:-}; backup=${3:-}
[[ ($mode == check || $mode == replace) && -f $key && -f $backup ]] || {
  echo "Usage: bash deploy/restore.sh check|replace KEY_FILE BACKUP.dump.age" >&2; exit 2; }
for tool in age docker; do command -v $tool >/dev/null || { echo "$tool is not installed." >&2; exit 1; }; done

summary_sql="SELECT 'schema version', version_num FROM alembic_version
UNION ALL SELECT 'accounts', count(*)::text FROM users
UNION ALL SELECT 'teams', count(*)::text FROM teams
UNION ALL SELECT 'players', count(*)::text FROM players
UNION ALL SELECT 'periods', count(*)::text FROM periods
UNION ALL SELECT 'assessments', count(*)::text FROM assessments
UNION ALL SELECT 'ratings', count(*)::text FROM ratings
UNION ALL SELECT 'saved plans', count(*)::text FROM player_plans
UNION ALL SELECT 'latest assessment', coalesce(max(updated_at)::text, 'none') FROM assessments;"

if [[ $mode == check ]]; then
  name="tapline-idp-restore-check-$$"
  trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT
  docker run -d --rm --name "$name" -e POSTGRES_USER=assessment_owner -e POSTGRES_DB=assessment \
    -e POSTGRES_PASSWORD=restore-check-only postgres:17-alpine >/dev/null
  for _ in $(seq 60); do docker exec "$name" pg_isready -U assessment_owner -d assessment >/dev/null 2>&1 && break; sleep 1; done
  sleep 2  # the image restarts the server once after its first-run setup
  for _ in $(seq 30); do docker exec "$name" pg_isready -U assessment_owner -d assessment >/dev/null 2>&1 && break; sleep 1; done
  # Privileges name the app's database user, which this throwaway server doesn't have; the data is what's checked.
  age -d -i "$key" "$backup" | docker exec -i "$name" pg_restore -U assessment_owner -d assessment --no-privileges --exit-on-error
  echo "Restored $(basename "$backup") into a throwaway database:"
  docker exec "$name" psql -U assessment_owner -d assessment -At -F ': ' -c "$summary_sql"
  echo "Restore check passed."
  exit 0
fi

cd "$(dirname "$0")/.."
if [[ -f .env.prod ]]; then compose=(docker compose --env-file .env.prod -f compose.yaml -f compose.prod.yaml); stack=production
elif [[ -f .env.dev ]]; then compose=(docker compose --env-file .env.dev -f compose.yaml -f compose.dev.yaml); stack=development
else echo "Run this in a deployment directory (with .env.prod or .env.dev)." >&2; exit 1; fi

# Reading only the start stops age early, which pipefail would count as a failure.
magic=$(set +o pipefail; age -d -i "$key" "$backup" 2>/dev/null | head -c 5)
[[ $magic == PGDMP ]] || { echo "That file doesn't decrypt to a PostgreSQL backup with this key." >&2; exit 1; }
echo "This replaces the $stack database with $(basename "$backup")."
echo "Everything recorded since that backup was taken will be lost (a backup of the current database is taken first)."
read -r -p "Type 'replace $stack' to continue: " answer
[[ $answer == "replace $stack" ]] || { echo "Nothing changed."; exit 1; }

bash deploy/backup.sh pre-restore
"${compose[@]}" stop api web
psql_owner=("${compose[@]}" exec -T db psql -v ON_ERROR_STOP=1 -U assessment_owner)
"${psql_owner[@]}" -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'assessment' AND pid <> pg_backend_pid();" >/dev/null
"${psql_owner[@]}" -d postgres -c "DROP DATABASE assessment;" -c "CREATE DATABASE assessment OWNER assessment_owner;"
age -d -i "$key" "$backup" | "${compose[@]}" exec -T db pg_restore -U assessment_owner -d assessment --exit-on-error
# Database- and schema-level access isn't part of a dump; give the app's user its access back (as on first start).
"${psql_owner[@]}" -d assessment <<'SQL'
GRANT CONNECT ON DATABASE assessment TO assessment_app;
GRANT USAGE ON SCHEMA public TO assessment_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO assessment_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO assessment_app;
ALTER DEFAULT PRIVILEGES FOR ROLE assessment_owner IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO assessment_app;
ALTER DEFAULT PRIVILEGES FOR ROLE assessment_owner IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO assessment_app;
SQL
"${psql_owner[@]}" -d assessment -At -F ': ' -c "$summary_sql"
# A backup from an older release is brought up to this release's schema before the app starts.
"${compose[@]}" run --rm migrate
"${compose[@]}" up -d --no-build api web
echo "Restored. Check the app, then delete the key file from this server."
