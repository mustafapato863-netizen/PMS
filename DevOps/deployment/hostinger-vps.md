# Hostinger VPS Deployment

This runbook deploys the PMS Dashboard monorepo as one Docker Compose project while keeping the frontend, backend, migration job, Redis, and TLS gateway as separate runtime services.

## Runtime architecture

```text
Internet -> Caddy (automatic HTTPS)
             |-- / and static assets -> React/Nginx
             |-- /api/*              -> FastAPI
             `-- /socket.io/*        -> FastAPI Socket.IO

FastAPI -> Supabase PostgreSQL
        -> private Redis container
```

Only ports 80 and 443 are published. PostgreSQL, Redis, FastAPI, and the frontend container are not exposed directly. Redis stays on an internal-only network; the backend and migration job also use an unexposed egress network so they can reach Supabase securely.

## Hostinger prerequisites

1. A Hostinger VPS using the Ubuntu Docker template.
2. The production domain `A`/`AAAA` record points to the VPS.
3. TCP ports 80 and 443 and UDP port 443 are open; SSH remains restricted to trusted administration sources.
4. The Supabase production connection string is available with `sslmode=require`.
5. Production data has a verified backup and a staging migration has already passed.

## GitHub configuration

Create a protected GitHub Environment named `production`. Add:

### Secrets

- `HOSTINGER_API_KEY`: Hostinger hPanel API token.
- `DATABASE_URL`: Supabase PostgreSQL connection string.
- `JWT_SECRET`: at least 32 random bytes.
- `REDIS_PASSWORD`: a strong URL-safe password.
- Private repositories require a GitHub deploy key configured for the VPS as described by Hostinger; no personal token is passed to the workflow.

### Variables

- `HOSTINGER_VM_ID`: numeric Hostinger VPS identifier.
- `APP_DOMAIN`: production hostname without scheme.
- `ACME_EMAIL`: email used for certificate issuance notices.

Require manual approval on the `production` environment for the first deployment. The workflow uses Hostinger's official `hostinger/deploy-on-vps@v2` action and runs only after `CI` succeeds on `main`, or by an explicitly approved manual dispatch.

## Local/staging verification

Copy the template outside Git and replace every placeholder:

```bash
cp DevOps/.env.hostinger.example DevOps/.env.hostinger
docker compose --env-file DevOps/.env.hostinger -f compose.production.yml config --quiet
docker compose --env-file DevOps/.env.hostinger -f compose.production.yml build
docker compose --env-file DevOps/.env.hostinger -f compose.production.yml up -d
docker compose --env-file DevOps/.env.hostinger -f compose.production.yml ps
```

The `migrate` service must complete successfully before the backend starts. Verify:

```bash
curl --fail https://YOUR_DOMAIN/healthz
curl --fail https://YOUR_DOMAIN/api/health/liveness
curl --fail https://YOUR_DOMAIN/api/health/readiness
```

Then test login, RBAC, team/employee scope, dashboards, Excel upload, reports, notifications, exports, and Socket.IO.

For an SSH-driven deployment on the VPS, run `PMS_ENV_FILE=/absolute/path/to/.env.hostinger DevOps/scripts/deploy.sh` from the checked-out repository.

## Rollback

1. Keep the previous Git release tag and database backup.
2. Redeploy the previous tag through the protected GitHub environment.
3. Do not downgrade the database automatically. Apply an Alembic downgrade only after reviewing the migration and confirming a compatible backup.
4. Caddy certificate and Redis/data volumes persist across image rollbacks.

If the previous SHA-tagged images still exist on the VPS, an operator can run `PREVIOUS_APP_VERSION=<commit-sha> DevOps/scripts/rollback.sh`. The script deliberately skips the migration service and never downgrades the database.
