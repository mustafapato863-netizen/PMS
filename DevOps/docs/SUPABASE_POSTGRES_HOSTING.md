# Supabase PostgreSQL Hosting Runbook

This project uses Supabase as a managed PostgreSQL provider while keeping the existing FastAPI, SQLAlchemy, Alembic, JWT, RBAC, Redis/cache, and Excel-ingestion layers.

## Architecture

```text
React/Vite -> FastAPI -> SQLAlchemy -> Supabase PostgreSQL
                         -> optional Redis-compatible cache
```

Do not add `@supabase/supabase-js` to the frontend for PMS core tables. Direct browser queries would create a second data path and bypass the existing services, authorization scope, KPI calculations, upload transactions, and cache invalidation.

## Required Supabase values

From Supabase Dashboard > Connect, obtain a PostgreSQL/SQLAlchemy connection string. The backend needs the database connection string, not the browser publishable key.

Use a connection string with TLS enabled, for example:

```text
postgresql://<db-user>:<db-password>@<pooler-host>:<port>/<db-name>?sslmode=require
```

Keep the password in the hosting provider's secret manager. Never commit it, put it in `VITE_*`, or expose a Supabase secret/service-role key to the browser.

## Staging migration sequence

1. Take a backup of the current PMS PostgreSQL database.
2. Create a separate Supabase staging project or schema.
3. Set `DATABASE_URL` only in the Backend environment.
4. Keep `APP_ENV=staging`, `PMS_AUTO_SEED=false`, and a real `JWT_SECRET`.
5. Install backend dependencies and run:

```powershell
cd Backend
alembic upgrade head
alembic current
```

For local-only staging credentials, put the connection string in the ignored
`DevOps/.env.local`; the Backend loads it before the shared `.env`. In hosted
environments, inject `DATABASE_URL` through the platform secret manager instead.

6. Verify the expected migration head, tables, enums, indexes, unique constraints, and foreign keys.
7. Import data through the existing seeding/upload path, not direct frontend inserts.
8. Compare pre/post counts for teams, employees, performance records, KPI values, users, actions, planning records, and audit records.
9. Run the focused backend tests, health probes, API checks, and frontend regression suite.
10. Promote the same connection/secrets pattern to production only after reconciliation passes.

## Hosting environment contract

Required:

- `DATABASE_URL`: Supabase PostgreSQL connection string with TLS.
- `JWT_SECRET`: strong random secret, never the Supabase publishable key.
- `CORS_ALLOWED_ORIGINS`: explicit frontend origin(s), comma-separated; never `*` with credentials.

Recommended:

- `APP_ENV=production`
- `PMS_AUTO_SEED=false`
- `PORT`: supplied by the hosting platform; the Docker image reads it dynamically.
- `DATABASE_POOL_SIZE=5`
- `DATABASE_MAX_OVERFLOW=0` or a value allowed by the Supabase plan.
- `DATABASE_POOL_RECYCLE=1800`
- `REDIS_URL`: an external Redis-compatible service when running more than one backend replica. Without Redis, the app uses a process-local cache and should remain single-replica or accept non-shared cache state.

## Release operations

- Run `alembic upgrade head` as a release/migration job before starting new web replicas.
- Do not run migrations automatically from every web replica.
- Do not enable `PMS_AUTO_SEED` in production.
- Use `/api/health/liveness` for container liveness and `/api/health/readiness` for database/cache readiness.
- Confirm the host forwards its assigned `PORT` to the container.
- Confirm Socket.IO/WebSocket routing and CORS for the deployed frontend origin.

## Go-live acceptance

- Alembic reaches the expected head on Supabase.
- `/api/health/liveness` returns 200 without database access.
- `/api/health/readiness` returns healthy with the intended database and cache state.
- Login, RBAC, team scope, KPI scorecards, Excel upload, planning, reports, notifications, and exports work against the hosted database.
- Source and destination counts reconcile.
- No Supabase secret/service-role key appears in frontend bundles, Git, logs, or browser storage.
- Rollback procedure and the pre-migration backup have been tested.
