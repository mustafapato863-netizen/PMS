# Production Environment Requirements

Date: 2026-07-29

## Required environment variables

| Variable | Requirement |
|---|---|
| `APP_ENV` | Must be `production` |
| `DATABASE_URL` | Required PostgreSQL/pooler URL; no SQLite fallback |
| `JWT_SECRET` | Required strong secret; no repository/default value |
| `JWT_ALGORITHM` | Explicitly approved algorithm |
| `JWT_EXPIRE_MINUTES` | Explicit bounded lifetime |
| `AUTH_REFRESH_SESSION_HOURS` | Non-remembered refresh-session lifetime; default `8` |
| `AUTH_REMEMBER_SESSION_DAYS` | Explicit Remember me refresh-session lifetime; default `30` |
| `AUTH_COOKIE_SECURE` | Must be `true` for HTTPS production |
| `AUTH_COOKIE_SAMESITE` | `none` for split-origin hosting, with Secure cookies |
| `AUTH_COOKIE_DOMAIN` | Optional shared parent-domain cookie scope |
| `CORS_ALLOWED_ORIGINS` | Comma-separated exact frontend origins |
| `PMS_DATA_DIR` | `/tmp` only for ephemeral work, otherwise external storage |
| `REDIS_URL` | Required only if shared cache/session revocation is enabled |
| `REDIS_SOCKET_TIMEOUT_SECONDS` | `0.25` recommended; must be greater than zero |
| `REDIS_RETRY_INTERVAL_SECONDS` | `30` recommended; zero or greater |
| `PMS_REALTIME_MODE` | `disabled` on Vercel; `in_process` only on an approved single-process host |
| `PMS_REPORT_CENTER_ENABLED` | `false` until Reports Center staging, export, and authorization checks pass; then enable by role/release |
| `DATABASE_POOL_SIZE` | Sized for provider and serverless concurrency |
| `DATABASE_MAX_OVERFLOW` | Usually zero with a transaction pooler |
| `DATABASE_POOL_RECYCLE` | Below provider idle timeout |
| `MAX_UPLOAD_BYTES` | Explicit approved upload ceiling |
| `PMS_AUTO_SEED` | `false` |
| `PMS_SEED_PERMISSIONS_ON_STARTUP` | `false`; use migrations/admin job |
| `PMS_SEED_DEMO_LEVELS` | `false` |
| `VITE_REALTIME_ENABLED` | `false` unless the backend explicitly uses `PMS_REALTIME_MODE=in_process` |
| `PMS_SCOPED_PERFORMANCE_API_ENABLED` | `false` until the bounded read-path rollout is approved; coordinate with the frontend flag |
| `PMS_SCOPED_PERFORMANCE_ALLOWED_ROLES` | Optional comma-separated role allow-list for scoped performance reads |
| `VITE_SCOPED_PERFORMANCE_API` | `false` until backend read-path and role rollout checks pass |
| `VITE_REPORT_CENTER_ENABLED` | `false` until the Reports Center backend flag and browser acceptance flows pass |

Documentation must use the exact runtime names. Existing references to `CORS_ORIGINS` and `JWT_SECRET_KEY` are incorrect.

## Database and serverless

- Use the Supabase transaction pooler or another serverless-safe pool endpoint where appropriate.
- Enforce connect, lock and statement timeouts.
- Keep per-instance pool size conservative.
- Monitor connection saturation and rejected connections.
- Migrations run as a controlled deployment step, not at function startup.
- Application startup must verify PostgreSQL, not create a local SQLite database.

## Filesystem

- Vercel function code is read-only except temporary storage.
- Team configuration files bundled with the deployment are read-only runtime assets.
- Uploads, reports and persistent artifacts belong in PostgreSQL or object storage.
- Import-time data-directory creation has been removed. Write paths must create only their required parent directory at the operation boundary.

## Redis and realtime

- Redis is lazy and shared; it does not ping at module import.
- Connect/read attempts use bounded timeouts and a retry cooldown with observable fallback behaviour.
- Process-local cache is an optimization only, never a distributed source of truth.
- Socket.IO is disabled by default on Vercel. Durable last-seen state belongs in PostgreSQL.
- If realtime delivery is required, use a provider/runtime that supports durable connections and a shared adapter.

## CORS and headers

- Explicit origins only.
- `allow_credentials` requires exact trusted origins.
- Add CSP, HSTS, `X-Content-Type-Options`, referrer policy and frame restrictions.
- Ensure file downloads use safe content types and filenames.

## Observability

Minimum production metrics:

- request p50/p95/p99 and status by normalized route,
- SQL query count/time per request,
- DB pool checkout/wait/failure,
- payload bytes,
- cache hit/miss/fallback,
- cold-start/import duration,
- upload rows/seconds and rollback outcomes,
- frontend Web Vitals and route request counts,
- deployment version and migration revision.

No employee names, JWTs, passwords or raw uploaded rows may appear in logs.

Implemented application telemetry includes `X-Request-ID`, `Server-Timing`,
`X-Response-Time-Ms`, normalized route, method, status, duration, and response
bytes. Database-pool, SQL-duration, Web Vitals, and production percentile
aggregation still require platform telemetry.

## Release gates

- frontend build and type check,
- backend focused/full tests,
- Alembic current equals expected head,
- upgrade and downgrade validated on a clone,
- authenticated smoke tests by role/scope,
- load tests only on local/staging/UAT data,
- rollback instructions and previous artifact available.
