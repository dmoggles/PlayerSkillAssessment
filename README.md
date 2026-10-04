# Player Skill Assessment

A team-based football assessment app for coaches. Coaches can maintain a roster, assess players in successive periods, compare coach and player ratings, confirm development priorities, and see progress across periods. Team owners can invite coaches and enable individual player self-assessment links.

The coach workspace has five areas: **Settings** (teams, periods, squad and access), **Assessment**, **Player Data** (summary, comparison, progress and confirmed priorities), **Team Data** (heatmaps), and **Development** (editing priorities). It uses a sidebar on large screens and a five-item bottom bar on phones. On phones, the current team/period/player appears in a compact bar; tap it to change the selection in a bottom sheet. Assessment shows one fully described skill card at a time within progress-labelled section accordions; swipe or use Previous/Next to move between skills. The selected team, period and player carry between relevant areas. Unsaved assessment or priority edits prompt before navigation. This is a responsive web app, not an offline PWA.

## Local start

Requires Docker Engine and Docker Compose v2. Run:

```bash
bash deploy/start_local.sh
```

Open <http://localhost:8080>. Test emails, including account verification and invitations, appear at <http://localhost:8025>. The script builds the images, starts PostgreSQL and Mailpit, applies migrations, then starts the app. Data lives in the `postgres_data` Compose volume and survives container restarts. PostgreSQL is bound only to `127.0.0.1:5433` for local tests; it is not exposed publicly.
Mailpit captures these development messages; they are not delivered to personal email inboxes. Open Mailpit on the host computer, then copy the verification link into the browser where you are using the app.

To reach the app from another device on the same network, set `WEB_BIND_HOST=0.0.0.0` and `PUBLIC_BASE_URL=http://YOUR-LAN-IP:8080` in a root `.env` file, then rerun `bash deploy/start_local.sh`. This exposes only the web port; PostgreSQL and Mailpit remain bound to localhost. Use the HTTPS VPS deployment for internet access.

Create an account, follow the verification email in Mailpit, sign in, create a team, add players, and create a period. Team owners may enable self-assessment in Team settings. When enabled, Settings → Player self-assessment shows each active player's status for the selected period (not sent, sent, opened, submitted, expired) and can create one-use, seven-day links for every player who still needs one. Links appear only once, so copy them individually or with Copy all and share them, for example in a team chat. Creating another link for a player revokes the old one.

Backend tests against the local database:

```bash
docker compose -f compose.yaml -f compose.local.yaml exec -T db createdb -U assessment_owner assessment_test
cd backend
DATABASE_URL=postgresql+psycopg://assessment_owner:local-owner-only@127.0.0.1:5433/assessment_test uv sync --frozen --extra test
DATABASE_URL=postgresql+psycopg://assessment_owner:local-owner-only@127.0.0.1:5433/assessment_test uv run alembic upgrade head
DATABASE_URL=postgresql+psycopg://assessment_owner:local-owner-only@127.0.0.1:5433/assessment_test PUBLIC_BASE_URL=http://testserver uv run pytest -q
```

Create `assessment_test` only once. Tests refuse to clear a database whose name does not end in `_test`.

Frontend checks: `cd frontend && npm ci && npm test && npm run lint && npm run build`.

## Access and data model

| Capability | Team owner | Team coach | Player link |
| --- | --- | --- | --- |
| Team settings, invitations, member roles, and deleting periods or the team | Yes | No | No |
| Roster (including restoring archived players), creating and renaming periods, assessments, priorities, and history | Yes | Yes | No |
| Issue/revoke self-assessment links when enabled | Yes | Yes | No |
| Submit assigned self-assessment once | No | No | Yes |

A team can have several owners but always keeps at least one; to transfer ownership, make another member an owner and then step down. Archiving a player marks them as having left the squad: their assessments, priorities and progress stay visible, but they are read-only and self-assessment links stop working until a coach restores them. Deleting a period permanently removes its assessments, self-assessment links and priorities. Deleting a team requires typing its name and removes all of its data and memberships.

Every player and period belongs to a team; API requests resolve team membership before reading or writing data. Coach assessments are shared per player and period. Saves include a version number to prevent silent overwrites, and each revision records the editor and ratings. The app uses the supplied skill matrix as a common starter template. No source-app database records are imported.

Passwords use Argon2. Email verification, expiring reset and invitation tokens, revocable HTTP-only sessions, CSRF tokens, and login throttling are built in. Raw player-link and account tokens are not stored. Link tokens (self-assessment `/self/…` and report `/report/…`) stay out of logs: the API container disables access logs, and both the web container's Nginx and the host Nginx templates turn access logging off for those paths. The app stores only player names for the roster; avoid entering unnecessary personal information in notes.

## VPS deployment

Development and production follow the same pattern as `football-data-collector` on a shared VPS: host Nginx terminates HTTPS, while separate Docker Compose projects bind their web containers to loopback ports 8083 (development) and 8082 (production). The existing football-data-collector ports 8081 and 8080 are untouched. PostgreSQL is internal to each Compose project and each project has its own persistent volume. The application connects as `assessment_app`; migrations connect as `assessment_owner`.

1. Create two distinct deployment directories owned by the deploy user, such as `~/player-assessment-dev` and `~/player-assessment`. Do not use the same directory for both: Compose uses the directory name to isolate volumes and containers. Copy [development.env.example](deploy/development.env.example) to `.env.dev` in the dev directory and [production.env.example](deploy/production.env.example) to `.env.prod` in the production directory. Set different database passwords, keep these files off Git and mode `600`, and percent-encode reserved characters in database URL passwords. Set `PUBLIC_BASE_URL` to each environment's exact HTTPS origin and `SECURE_COOKIES=true`.
2. Point two DNS names at the VPS. Copy [the Nginx setup script](deploy/setup_host_nginx.sh), [production template](deploy/nginx-prod.conf.example), and [development template](deploy/nginx-dev.conf.example) to the same directory on the VPS. From that directory, run `sudo bash setup_host_nginx.sh YOUR_PROD_DOMAIN YOUR_DEV_DOMAIN YOUR_CERTBOT_EMAIL`. It checks for existing sites, asks you to confirm the DNS results, installs and tests the two host Nginx sites, reloads Nginx, and requests HTTPS certificates with Certbot. If a certificate request fails, the HTTP sites remain installed; resolve DNS/port 80 and rerun the failed Certbot command rather than rerunning the setup script. Host sites installed before report links existed should add the `location ~ ^/(api/)?(self|report)/` block from the current templates (it disables access logging for link tokens), then run `sudo nginx -t && sudo systemctl reload nginx`. Only host Nginx needs public ports 80/443; do not open 8082, 8083, or PostgreSQL ports. The two new sites must have hostnames distinct from the existing TapLine sites.
3. Production requires a transactional SMTP relay for verification, invitations, and resets. Development uses Mailpit at `127.0.0.1:8025` on the VPS; use an SSH tunnel to view its inbox. For private GHCR packages, sign the VPS deploy user into GHCR once with a read-only package token.
4. In this repository, create GitHub environments named `development` and `production`. In **each** environment set `SSH_HOST`, `SSH_PORT`, `SSH_USER`, `SSH_PRIVATE_KEY`, and `DEPLOY_PATH` (the absolute path to that environment's deployment directory). These are distinct from secrets in `football-data-collector`; GitHub does not share repository environment secrets. The deploy user needs Docker permissions and write access to both directories. Protect the production environment as appropriate. These workflows match `football-data-collector` and do not pin the SSH server's host-key fingerprint; if stronger host verification is needed later, add a verified fingerprint to both SSH actions.
5. Every push to `main` runs tests, publishes `:dev` and commit-SHA images, then deploys development. Publishing a GitHub release runs tests, publishes the release-tagged and `:latest` images, then deploys that exact release tag to production. Both workflows copy Compose files, pull images, start their database, run migrations, restart the app, and check `/api/health` through the local web port. The workflows do not create `.env.dev`, `.env.prod`, DNS, or Nginx sites.

If an older version of this app has already created production data on this VPS, preserve its Compose project name and volume when choosing the production directory. Do not switch to a new directory or remove an old volume until the data has been backed up and migrated. Stop any old Caddy container for this app before enabling the new host Nginx sites. Database migrations are forward-only operationally: inspect a migration and take a backup before applying one that removes or rewrites data. To roll back app code, set both image names in `.env.prod` to the desired release tag and run `docker compose --env-file .env.prod -f compose.yaml -f compose.prod.yaml up -d --no-build api web`; a code rollback does not reverse database migrations.

### Player reports

Player Data → Report shows a printable report for the selected player and period (coach ratings and priority notes only; rating notes, overall notes and self-ratings are never included). Coaches can add a message to the player and create a read-only share link that works without signing in for 30 days. Creating a new link replaces the old one; links can be revoked, and deleting the period or team removes them. Creating and revoking links is recorded in Activity.

### Maintenance and audit log

The API removes expired sessions, email links and stale sign-in throttle records every 6 hours (`CLEANUP_INTERVAL_HOURS`); run `python -m app.maintenance` in the API container to do it on demand. Expired self-assessment links are kept so the squad board can show them. Team owners can see an Activity list under Team access: invitations, joins, role changes, removals, period and team deletions, and team setting changes. Audit events keep the email addresses involved and are retained after a team is deleted.

The interactive API docs (`/api/docs`) and schema (`/api/openapi.json`) are served only when `API_DOCS_ENABLED=true`, which the local Compose override sets. Development and production deployments do not expose them unless you add that setting to their env file.

### Versions

Each image carries the version it was built from. The app shows it in the sidebar and under Settings → Account, and `/api/health` returns it. Production uses the GitHub release tag (use semantic versions such as `v0.1.0`), development uses `dev-<short commit>`, and local builds use `git describe --tags --always --dirty` (for example `v0.1.0-3-gabc1234`, or a short commit with `-dirty` for uncommitted changes).

### Backups and restore checks

Configure an off-host S3-compatible bucket with access limited to backups, versioning, and a 30-day retention policy. Generate an `age` key pair, keep the private key off the VPS, and set `BACKUP_AGE_RECIPIENT` and `BACKUP_S3_URI` in the backup job environment. Schedule `bash deploy/backup.sh` nightly using a timer or cron. The script streams a custom-format PostgreSQL dump through `age` encryption to the bucket; it does not write a plaintext dump to disk.

Monthly, restore a backup into a separate database and verify its tables and representative row counts. From the deployment directory, for example:

```bash
docker compose --env-file .env.prod -f compose.yaml -f compose.prod.yaml exec -T db createdb -U assessment_owner assessment_restore
aws s3 cp s3://YOUR-BUCKET/YOUR-BACKUP.dump.age - | age -d -i /secure/off-host/age-key.txt | docker compose --env-file .env.prod -f compose.yaml -f compose.prod.yaml exec -T db pg_restore -U assessment_owner -d assessment_restore --no-owner
docker compose --env-file .env.prod -f compose.yaml -f compose.prod.yaml exec -T db psql -U assessment_owner -d assessment_restore -c 'SELECT count(*) FROM assessments;'
```

The backup destination, SMTP relay, DNS names, Nginx sites, and VPS credentials are deployment prerequisites; no server is configured by this repository alone.

### Seed the development deployment

Once the latest development API image has deployed and migrations have run, SSH to the VPS and run this from the **development** deployment directory (the one containing `.env.dev`):

```bash
cd /path/to/player-assessment-dev
bash deploy/seed_dev_host.sh
```

The script requires an interactive confirmation and a development-looking `PUBLIC_BASE_URL`. It creates verified `dev-owner@example.com` and `dev-coach@example.com` logins, two separate teams (one with self-assessment enabled), ten synthetic players, three periods per team, varied coach/player ratings with a few coach notes, and confirmed priorities in the earlier periods so the current period shows priority follow-up (some players already have current priorities; others are ready for Keep). Ratings are random but reproducible: every run regenerates the demo teams' assessments, notes and priorities to the same values, discarding demo edits. The second login also has coach access to the first team. It does not email anyone. It is safe to rerun without duplicating records and upgrades earlier `@example.invalid` demo logins in place, but each run **rotates both demo passwords and revokes their sessions**. Copy the freshly printed credentials to a password manager; they are not written to a file. Never run this against production or use these accounts for real player data.
