#!/usr/bin/env bash
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=app_password="$APP_DB_PASSWORD" <<'SQL'
CREATE ROLE assessment_app LOGIN PASSWORD :'app_password';
GRANT CONNECT ON DATABASE assessment TO assessment_app;
GRANT USAGE ON SCHEMA public TO assessment_app;
ALTER DEFAULT PRIVILEGES FOR ROLE assessment_owner IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO assessment_app;
ALTER DEFAULT PRIVILEGES FOR ROLE assessment_owner IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO assessment_app;
SQL
