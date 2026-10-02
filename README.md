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

Create an account, follow the verification email in Mailpit, sign in, create a team, add players, and create a period. Team owners may enable self-assessment in Team settings. When enabled, coaches can issue a one-use, seven-day link for a player in the active period; copy it when it appears. Issuing another link revokes the old one.

Backend tests against the local database:

```bash
docker compose exec -T db createdb -U assessment_owner assessment_test
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
| Settings and invitations | Yes | No | No |
| Roster, periods, assessments, priorities, and history | Yes | Yes | No |
| Issue/revoke self-assessment links when enabled | Yes | Yes | No |
| Submit assigned self-assessment once | No | No | Yes |

Every player and period belongs to a team; API requests resolve team membership before reading or writing data. Coach assessments are shared per player and period. Saves include a version number to prevent silent overwrites, and each revision records the editor and ratings. The app uses the supplied skill matrix as a common starter template. No source-app database records are imported.

Passwords use Argon2. Email verification, expiring reset and invitation tokens, revocable HTTP-only sessions, CSRF tokens, and login throttling are built in. Raw player-link and account tokens are not stored. The API container disables access logs so player-link tokens do not appear in URL logs. The app stores only player names for the roster; avoid entering unnecessary personal information in notes.

## VPS deployment

The target is one VPS running Docker Compose, with separate web, API, and PostgreSQL containers. Caddy terminates HTTPS. PostgreSQL has a persistent volume and is not internet-facing. The application connects as `assessment_app`; migrations connect as `assessment_owner`.

1. Point the desired domain at the VPS. Install Docker Engine with Compose v2, `age`, and the AWS CLI (or an S3-compatible CLI configuration). Open ports 80 and 443. Create a deployment directory, then copy [production.env.example](deploy/production.env.example) to `.env` in that directory and fill in every value. Keep `.env` readable only by the deploy user. Percent-encode reserved characters in database URL passwords. Set `PUBLIC_BASE_URL` to the exact HTTPS origin and `SECURE_COOKIES=true`.
2. Configure a transactional SMTP relay for verification, invitations, and resets. For private GHCR packages, sign the VPS into GHCR once with a read-only package token. Set `API_IMAGE` and `WEB_IMAGE` to the lower-case GHCR image names for this repository.
3. Add GitHub Actions secrets `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_PATH`, `DEPLOY_SSH_KEY`, and `DEPLOY_KNOWN_HOSTS` to the `production` environment. `DEPLOY_KNOWN_HOSTS` must contain the pinned SSH host key. The deploy user needs Docker permissions and write access to `DEPLOY_PATH`. Protect the production environment as appropriate for your team.
4. Push to `main`. The workflow tests, builds and publishes both images, copies the Compose/Caddy files to the VPS, migrates the database, starts the services, and checks the local web-to-API health route. The first deployment creates the PostgreSQL volume and role. Later deployments retain the volume.

The workflow publishes both `latest` and commit-SHA image tags. To roll back app code, set `API_IMAGE` and `WEB_IMAGE` in the VPS `.env` to a prior SHA tag and run `docker compose -f compose.yaml -f compose.prod.yaml up -d --no-build`. Database migrations are forward-only operationally: inspect a migration and take a backup before applying one that removes or rewrites data.

### Backups and restore checks

Configure an off-host S3-compatible bucket with access limited to backups, versioning, and a 30-day retention policy. Generate an `age` key pair, keep the private key off the VPS, and set `BACKUP_AGE_RECIPIENT` and `BACKUP_S3_URI` in the backup job environment. Schedule `bash deploy/backup.sh` nightly using a timer or cron. The script streams a custom-format PostgreSQL dump through `age` encryption to the bucket; it does not write a plaintext dump to disk.

Monthly, restore a backup into a separate database and verify its tables and representative row counts. From the deployment directory, for example:

```bash
docker compose -f compose.yaml -f compose.prod.yaml exec -T db createdb -U assessment_owner assessment_restore
aws s3 cp s3://YOUR-BUCKET/YOUR-BACKUP.dump.age - | age -d -i /secure/off-host/age-key.txt | docker compose -f compose.yaml -f compose.prod.yaml exec -T db pg_restore -U assessment_owner -d assessment_restore --no-owner
docker compose -f compose.yaml -f compose.prod.yaml exec -T db psql -U assessment_owner -d assessment_restore -c 'SELECT count(*) FROM assessments;'
```

The backup destination, SMTP relay, domain, and VPS credentials are deployment prerequisites; no production server is configured by this repository alone.
