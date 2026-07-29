# PMS Performance and Compatibility Current-State Audit

Date: 2026-07-29
Scope: local production-equivalent React/FastAPI/PostgreSQL stack
Phase gate: audit and baseline only; no optimisation was applied before this document.

## Executive conclusion

The stack is functionally connected and buildable, but three current read flows are not production-ready at the measured local data volume: Insights, Planning filter options, and Report filter options. PostgreSQL is not the primary source of their latency. The strongest evidence points to repeated filesystem JSON loading, validation, Python model reconstruction, and large response generation.

The current architecture also has production configuration risks: an unsafe JWT fallback, import-time filesystem and Redis work, environment-variable documentation drift, process-local presence/cache assumptions on Vercel, and bearer tokens persisted in `localStorage`.

## Audited architecture

| Layer | Current implementation | Audit result |
|---|---|---|
| Frontend | React, TypeScript, Vite, React Router, TanStack Query | Production build passes; route-level lazy loading exists |
| API | FastAPI with JWT middleware, RBAC dependencies and common `/api` router | 118 OpenAPI operations; response envelopes are not fully canonical |
| Persistence | SQLAlchemy, Alembic, PostgreSQL 18.4 | Connected to local `PMS_Sys`; migration is at the single current head |
| Configuration | JSON team definitions plus versioned database configuration | Repeated file reads/validation are a measured hot path |
| Cache | Optional Redis plus process-local fallback and frontend query cache | Current keys/invalidation are not sufficiently scoped for all team responses |
| Realtime | Socket.IO with process-local connected-client state | Not durable across Vercel instances |
| Hosting | Separate Vercel manifests for frontend and backend | Backend limit is 60 seconds/1024 MB; filesystem and socket assumptions require hardening |

## Repository and migration state

- The root repository contains nested Backend and Frontend repositories.
- Both nested repositories were already dirty before this audit. Audit work did not revert or overwrite those changes.
- Alembic current/head: `e4a7c1d9b520`.
- Historical branchpoints are merged into the current line. Upgrade ordering must continue through Alembic rather than manual DDL.
- Local PostgreSQL exposes 55 application tables including yearly performance partitions.

## Runtime data inventory

| Relation | Rows observed |
|---|---:|
| performance_records | 1,015 |
| kpi_values | 3,663 |
| employees | 300 |
| management_kpi_config | 1,086 |
| management_kpi_snapshots | 1,086 |
| audit_log | 59,222 |
| error_logs | 764 |
| notifications | 191 |
| notification_recipients | 129 |

The 2026 performance partition contains the active rows. Other configured yearly partitions are currently empty.

## Major flow audit

### Authentication and authorisation

- JWT bearer tokens and the user/session object are stored in browser `localStorage`.
- Each protected request validates the token and queries the active user in an authentication session.
- Route dependencies commonly open a second SQLAlchemy session.
- Backend role enforcement uses the database user role; it does not trust `X-User-Role` when JWT state exists.
- Logout clears authentication storage but does not clear the TanStack Query cache.
- Error contracts differ between authentication middleware, generic middleware, and FastAPI validation.

### Dashboard, Insights, Planning and Reports

- Dashboard records are filtered in SQL and eager-load KPI, employee and team relationships.
- Each returned record then resolves and validates a team JSON configuration.
- Insights, Planning options and Report options rebuild broad authorized record collections.
- Instrumentation proves database time is a minority of their total wall time.
- `/api/performance` and `/api/performance/records` currently return the same large record payload for the measured scope.

### Upload and promotion

- File-size validation is present.
- Upload processing persists batches/logs and uses explicit commit/rollback paths.
- No destructive upload/promotion benchmark was executed because the audited local database contains shared working data and no isolated fixture transaction was documented.
- Promotion and rollback must be benchmarked later with a disposable database clone or transactionally isolated fixture.

### Cache and realtime

- Redis failure falls back to process memory.
- Current team cache keys omit region, performance level, configuration version and authorization scope.
- There is no observed TTL jitter or stampede control.
- Socket connected-client state is process-local and cannot be treated as authoritative presence on Vercel.

## Compatibility findings

1. Frontend and backend generally agree on active route names, including Insights, Planning, Reports, Settings and Team Management.
2. The employee-profile hook adds a trailing slash to a parameterized endpoint whose OpenAPI route has no trailing slash. This can add a redirect round-trip.
3. Frontend code supports several incompatible error shapes rather than consuming one API error contract.
4. Manual `fetchWithRole` calls remain alongside `apiFetch`, creating inconsistent 401 handling, JSON parsing, cancellation and cache participation.
5. Deployment documentation uses `CORS_ORIGINS`/`JWT_SECRET_KEY`, while runtime reads `CORS_ALLOWED_ORIGINS`/`JWT_SECRET`.

## Security and production risks

| Severity | Finding | Required action |
|---|---|---|
| Critical | Production can start with a built-in JWT fallback secret | Fail startup when `JWT_SECRET` is absent or unsafe |
| High | Bearer token persists in `localStorage` | Retain temporarily; document XSS exposure and evaluate same-site HttpOnly cookie migration |
| High | User-scoped React Query data survives logout | Clear query cache during logout and 401 teardown |
| High | Import-time `os.makedirs` writes to the default backend data path | Require `/tmp` or external object storage on Vercel |
| Medium | Redis `PING` occurs during import | Make connection lazy and observable |
| Medium | Presence is process-local | Persist durable `last_seen_at`; treat Socket.IO status as best-effort only |
| Medium | Health subroutes may not be auth-exempt | Explicitly exempt liveness/readiness or document protected probes |

## Prioritized measured opportunities

1. Cache parsed and validated team configuration by file identity/mtime, returning isolated values and invalidating safely when files change.
2. Reduce repeated record reconstruction and repeated full-scope options generation.
3. Introduce summary/option projections rather than returning full dashboard record payloads where consumers need only dimensions.
4. Unify frontend request handling and clear user-scoped query data on logout.
5. Add production configuration fail-fast checks and remove import-time network/filesystem work.

## Explicit non-findings

- The representative June 2026 performance SQL completes in 2.70 ms. No new database index is justified for that query at the current scale.
- No KPI formula, grade threshold, reporting-period rule, visibility rule or configuration-version rule was changed.
- No production load or destructive test was run.
