# Findings & Decisions

## Requirements
- Audit frontend/backend API compatibility and backend/PostgreSQL compatibility.
- Measure current latency, query count/time, payload size, request count, rendering, cold/warm behaviour, and representative major flows.
- Identify duplicate calls, N+1 queries, slow SQL, missing justified indexes, payload waste, and unsafe serverless assumptions.
- Preserve authentication, authorisation, team/performance-level isolation, reporting periods, configuration versions, KPI formulas, and grade mappings.
- Add only measured, scoped, reversible optimisations with documented invalidation and rollback.
- Produce the ten requested audit, architecture, baseline, results, environment, rollback, and final-report documents.
- Implement the accepted recommendations in staged, release-safe increments, beginning with production configuration security, session cache isolation, and the verified Pharmacy fixture mismatch.

## Research Findings
- Project stack is React/TypeScript, FastAPI/Python, SQLAlchemy/Alembic, PostgreSQL, optional Redis, Socket.IO, and Vercel deployment.
- The working tree already contains unrelated user changes in both nested Backend and Frontend repositories; audit work must preserve them.
- The currently running backend was previously verified against local PostgreSQL `PMS_Sys`; all baseline commands must re-confirm the target without exposing credentials.
- The request explicitly requires audit and baseline before any implementation.
- Repository layout is a parent Git repository with `Backend` and `Frontend` Git submodules; both submodules are already dirty with prior user work.
- Backend runtime entrypoint is `Backend/app.py`: FastAPI app, request timing middleware, authentication middleware, error middleware, explicit CORS origins, `/api` router mount, optional Socket.IO ASGI wrapper, and optional non-Vercel startup seeding.
- Frontend runtime entrypoint is `Frontend/src/main.tsx`: React StrictMode, a shared TanStack Query client, Web Vitals reporting only when a production endpoint is configured, and `App.tsx`.
- `App.tsx` lazy-loads major routes. Reports, Insights, Planning, and Team Management are guarded in the client; backend authorisation must remain canonical.
- Frontend initialisation order is AuthProvider → RoleProvider → router/application. Notification Socket.IO starts only after authentication initialisation reaches `ready`.
- Local override files exist in both `DevOps/.env.local` and `Backend/.env.local`; environment precedence and secret-safe reporting require explicit audit.
- Vercel manifests exist independently in Backend and Frontend.
- Frontend authentication is bearer-token based: JWT and a user/session object are stored in `localStorage`; there is no cookie-auth flow in the audited implementation.
- `apiFetch` adds both `Authorization` and `X-User-Role`; backend authentication derives the role from the active database user and does not trust the header on authenticated requests.
- Logout clears authentication localStorage but does not currently clear the TanStack Query cache, creating a user-scoped client-cache hygiene risk on shared browsers.
- TanStack Query already provides global request deduplication with 2-minute stale time, 10-minute garbage collection, no focus refetch, reconnect refetch, and two query retries.
- Error responses are not canonical: authentication middleware returns `{success,message}`, generic middleware returns `{success,message,request_id}`, while FastAPI validation/HTTP errors use `detail`; the frontend contains compatibility parsing for multiple shapes.
- Every authenticated HTTP request opens one middleware database session to load the active user; route dependencies can open an additional request session. This is a candidate for query-count measurement and request-scoped reuse.
- Database engine is module-global and sessions close through generator/finally. Hosted defaults are pool size 5, overflow 0, recycle 1800, pre-ping enabled, but connect/read statement timeouts are not configured in the engine.
- `config/settings.py` creates `PMS_DATA_DIR` at import time. With the default Backend data directory this is an import-time filesystem write attempt and needs explicit Vercel compatibility verification.
- Production has an unsafe JWT fallback when `JWT_SECRET` is missing instead of failing configuration validation.
- Redis client performs a synchronous `PING` at module import with 1-second connect/read timeouts. This can add cold-start latency; outage falls back to process-local LRU cache.
- Existing cache keys are `performance:{employee}:{month}:{year}` and `team_performance:{team}:{month}:{year}`. Team keys omit region, performance level, configuration version, and user scope; usage must be audited before they can be considered safe for scoped responses.
- Existing cache invalidation supports per-record, per-team, prefix scan, pub/sub notification, and `flushdb`; no TTL jitter or stampede protection was observed in the current service.
- Socket presence and connected-client state are authoritative only within one process. The deployment document correctly warns that Vercel cannot provide durable Socket.IO connections, but runtime code still instantiates in-process Socket.IO when installed.
- Frontend Vercel serves immutable hashed assets and SPA rewrites; Vite manually splits vendor, charts, animation, and socket bundles.
- Deployment documentation is inconsistent with runtime variable names: it mentions `CORS_ORIGINS` and `JWT_SECRET_KEY`, while code reads `CORS_ALLOWED_ORIGINS` and `JWT_SECRET`.
- Live local OpenAPI exposes 118 operations across authentication, employee/performance, planning, insights, reports/story builder, configuration, upload, team management, notifications, and vitals.
- Static frontend search shows two request paths: canonical `apiFetch` and legacy/direct `fetchWithRole`. Major React Query hooks exist for Insights, Reports, Planning, team management, balanced scorecard, employee profile, KPI weights, global search, and performance data.
- Direct/manual requests remain in authentication, notifications, Settings upload/config panels, report generation/download, team export, employee row actions, and legacy performance data hooks; duplicate or uncancelled behaviour requires per-page measurement.
- Local PostgreSQL currently exposes 55 inspector-visible tables including yearly `performance_records` partitions. Representative sizes: 1,015 performance records, 3,663 KPI values, 300 employees, 1,086 management config rows, 1,086 management snapshots, 59,222 audit rows, 764 error logs, 191 notifications, and 129 recipients.
- `performance_records` is partitioned by year with populated 2026 partition and empty 2020–2025/2027–2030/default partitions. Parent and child indexes overlap substantially and need plan/write-cost review rather than blind additions.
- Core uniqueness is present for employee external IDs, employee/month/year performance records, KPI record/key, team-level KPI config scope, management config/snapshot scope, upload team/month/year, user/team/level assignments, configuration versions, and report integrity/versioning.
- Potential index review candidates based on observed table metadata (not yet justified by plans): `error_logs`, `notifications`, staging tables, upload batches, onboarding drafts, and plan child tables have no explicit secondary indexes despite likely filtered list/history paths.
- Alembic directory contains 31 revisions including configuration versioning, staging/visibility, reporting, planning, management snapshots, performance/audit indexes, user identity/presence, and yearly partition-related schema evolution.
- Warm local HTTP measurements identify three dominant read bottlenecks: Insights p50 6.99 s, Planning options p50 5.01 s, and Report options p50 3.37 s.
- Instrumented single-request probes show SQL is a minority of those wall times: Insights 14 queries / 233 ms SQL / 5.61 s wall; Planning options 16 / 207 ms / 3.40 s; Report options 12 / 207 ms / 3.16 s.
- The dominant non-SQL evidence is repeated JSON configuration loading and validation inside per-record mapping. One Insights request emitted hundreds of repeated configuration-loader events.
- The June 2026 performance endpoint returns 597,829 bytes and has a warm p50 of 943 ms; `/records` returns the same payload and has a warm p50 of 1.40 s.
- The representative partition-pruned performance query executes in 2.70 ms for 186 rows. At the current 1,015-row scale PostgreSQL correctly chooses a sequential scan of the 2026 partition; this does not justify adding another month/year index.
- PostgreSQL `pg_stat_statements` is not installed in the local environment, so repository-level instrumentation and explicit EXPLAIN evidence are the available sources.
- Frontend production build succeeds. Largest gzip chunks are charts 112.70 kB, vendor 71.04 kB, app entry 64.46 kB, team dashboard 48.76 kB, and animation 43.28 kB.
- After mtime-aware parsed-config caching plus per-request resolved-config reuse, serial warm p50 measurements were: Performance 367 ms, Planning options 1,986 ms, Report options 1,486 ms, Insights 1,647 ms. Response byte counts and SHA-256 bodies matched the pre-change responses for all four flows.
- Focused backend regression suite passed 129 tests. The full frontend suite initially had eight 5-second timeouts while running concurrently with backend/database verification; this requires an isolated rerun before classification.
- Interim Phase 6 result was 506 passed / 3 stale Pharmacy-fixture failures; current-column fixture corrections later brought the final backend suite to 538/538 without changing scoring semantics.
- Interim Phase 6 frontend result was 182 passed / 1 default-timeout failure; the final serial suite passes 187/187, and build, typecheck, lint, and targeted browser checks pass.
- Production safety gaps are concrete in runtime code: `config/settings.py` still supplies a fixed JWT fallback, `config/database.py` falls back to SQLite whenever `DATABASE_URL` is absent, and `app.py` can run automatic seed paths from environment flags.
- Frontend logout removes authentication keys but leaves the shared TanStack Query cache intact; the terminal 401 path independently removes the same keys and also needs the same query cancellation and cache purge.
- The three Pharmacy failures use `A.NoofPrescriptionsContribution`, while the authoritative current team configuration reads actual values from `NoofPrescriptionAch%` and targets from `T.NoofPrescriptionsContribution`.
- The worktree contains extensive unrelated user changes in both submodules. P0 edits must be limited to inspected security/session/test files and avoid broad formatting.
- The shared DevOps `.env` declares production, while the local override currently selects the local database but does not explicitly select development. Once fail-fast production checks are added, the local override must explicitly declare `APP_ENV=development` so local execution remains intentional.
- Production seed protection must cover all three startup paths: `PMS_AUTO_SEED`, `PMS_SEED_PERMISSIONS_ON_STARTUP`, and the directly-read `PMS_SEED_DEMO_LEVELS`.
- A shared asynchronous client-session reset can cancel active TanStack Query work and then clear the cache. Both explicit logout and non-login HTTP 401 handling can reuse it without creating a dependency cycle because the query-client module has no API-client dependency.
- The DevOps environment template currently uses `CORS_ORIGINS`, but runtime reads `CORS_ALLOWED_ORIGINS`; this is the exact documented mismatch to correct.
- Existing frontend API-client tests cover only message normalization. New tests are needed for the query-cache reset itself and for the terminal 401 path.
- `AuthContextProps.logout` is intentionally synchronous from the component API. Its implementation can trigger the asynchronous server logout and cache reset while immediately clearing React auth state; the cache helper will cancel first and clear after cancellation completes.
- Production settings validation should be built from pure helper functions plus module-level enforcement. This allows direct unit tests of missing, placeholder, and valid secrets without repeatedly mutating the process-wide imported settings module.
- `DevOps/.env` and `.env.local` are correctly ignored; only `.env.example` and deployment documentation are tracked. A local-only `APP_ENV=development` override can preserve the current workstation after production fail-fast checks without leaking into a release artifact.
- The CORS variable mismatch is operational, not documentation-only: both development and staging Compose files pass `CORS_ORIGINS`, and production Compose requires that unused name. These manifests must move to `CORS_ALLOWED_ORIGINS` together with the template and hosting guide.
- The backend's direct local default port is 8000, while the container image intentionally defaults to 7860. Documentation should distinguish direct-local and container/platform defaults rather than declaring one inaccurate global default.
- Focused tests prove the pure fail-fast rules and current Pharmacy contract, but the dotenv load order still allows `.env.local` to override process-provided deployment variables. Production environment variables must win over every file layer before the module-level enforcement is considered complete.
- Production Compose still overrides the backend's safe hosted connection defaults with `DATABASE_POOL_SIZE=20` and `DATABASE_MAX_OVERFLOW=10`; its manifest should align to the audited 5/0 serverless-safe defaults.
- Runtime source-of-truth search found one additional obsolete Vercel guide using both `CORS_ORIGINS` and `JWT_SECRET_KEY`; tracked deployment documentation now needs the same exact-name correction.
- `PMS_DATA_DIR` was resolved before dotenv layers were loaded. The environment loader refactor should also move this lookup after environment loading so the documented setting becomes effective.
- The complete backend suite now passes 523/523, including the three formerly failing Pharmacy cases.
- The complete frontend suite passes 185/185 with one Vitest worker and a 15-second bound; its default many-worker jsdom mode is resource-contention prone on this workstation. Lint, typecheck, and production build also pass.
- Phase 8 endpoint inventory confirms Planning and Reports already use dedicated `/options` calls, while Insights embeds filter options in `/api/insights/workspace`.
- Insights frontend consumers directly depend on `workspace.options` for period, region, team, level, position, employee, and KPI selectors, so removing embedded options would be a breaking change. Any separation must be additive or internally optimized first.
- The Insights service already returns people-contribution and KPI-trend sections only when one KPI is selected. The accepted lazy-calculation recommendation is therefore partially satisfied and should be preserved rather than reimplemented.
- Canonical authorization contains both broad role/team filtering and explicit team-level assignment filtering. SQL projection work must reproduce employee self-scope, manager team scope, and team-level scope—not just `accessible_teams`.
- Planning options currently call `InsightsService.authorized_records`, which fully maps both employee performance and management BSC records before extracting scalar options.
- Reports options call `DashboardRecordService.list_records` and then extract the same small scalar dimension set; this is a strong projection candidate because no KPI detail is used.
- A projection cannot be employee-table-only for Planning/Insights because the authorized source includes `ManagementBSCService.list_analysis_records`. Management option rows and employee option rows must share the same lightweight shape before canonical scope filters are applied.
- Existing SQL repository methods already filter dashboard records by explicit dimensions, but they do not accept authorization scope. A new option-row method should return only scalar identifiers/dimensions, then reuse the existing canonical in-memory scope filters to minimize security divergence.
- `DashboardRecordService.list_records` performs configuration resolution, legacy KPI repair, Pydantic record validation, and KPI serialization for every row. None of that work is needed by Reports options.
- Management analysis records are built only for snapshot scopes with an active matching KPI configuration. A management option projection must join snapshots to active configuration scope rather than returning every orphan snapshot.
- Existing ReportService unit tests inject a stub record service. The optimization should use a capability check/fallback so current test doubles and external callers retain compatibility.
- Planning options can switch to a merged employee/management scalar projection immediately; Insights workspace still needs KPI evidence for scoring and dynamic KPI options, so its full records cannot be replaced wholesale by scalar rows.
- Projection implementation passes 37 focused tests, including real SQL employee/management dimension rows, manager team-level isolation, and proof that Reports options does not call the full dashboard-record loader.
- The local backend is listening on port 8000; its health endpoint is protected by the current auth middleware, so performance probes must reuse the authenticated baseline method rather than assume an anonymous health check.
- The prior post-cache reference values for the endpoints being optimized are Planning options 1,985.53 ms / 20,274 bytes and Reports options 1,486.04 ms / 33,006 bytes. These are the correct comparison points for the new projection phase.
- The baseline method created a short-lived JWT for an existing active local Admin without recording secrets or employee data; the same read-only method remains appropriate.
- The first projection query used SQL `DISTINCT`, which changed overwrite order for a handful of employees with historical team/position rows. Removing unnecessary `DISTINCT` from the one-row-per-performance-record employee projection restores the legacy full-loader order and exact option output.
- Direct current-database comparisons now show semantic equality for both Reports options and Planning options between the legacy full-record path and the new projection path, with zero differing fields.
- Initial projection HTTP timing before that compatibility ordering adjustment was approximately 172 ms p50 for Planning options and 95 ms p50 for Reports options, showing the expected material gain. Final numbers must be re-collected after restart.
- Final five-sample warm HTTP results after the compatibility fix are Planning options 120.71 ms p50 / 20,274 bytes and Reports options 72.61 ms p50 / 33,006 bytes.
- Compared with the post-cache reference, scalar projections reduce Planning options p50 by 93.9% and Reports options p50 by 95.1%, while restoring the exact response byte counts.
- The restarted local Uvicorn worker is healthy on port 8000. Startup logs again show two synchronous Redis connection attempts before readiness, confirming the Phase 9 cold-start target with direct runtime evidence.
- Query instrumentation confirms projections halve database work as well as Python work: Planning options 16→8 SQL statements and Reports options 12→6. The Planning in-process wall sample includes Redis/startup overhead and is not used as the HTTP p50.
- The primary `/api/performance` payload cannot simply become summary-only: Team Dashboard, Employee Profile, Executive, KPI detail actions, and several team calculations actively use `raw_data` and `kpi_values`.
- Sidebar and Header currently subscribe to the same global full-performance hook only to derive navigation teams/months. On routes such as Settings, Planning, Reports, and Insights, this can trigger the approximately 598 kB raw payload even though those shell components do not need KPI evidence.
- A lightweight authorized performance catalog endpoint backed by option projections is the safe additive summary boundary. Migrating only the application shell to it preserves full detail on analytical pages while eliminating unnecessary raw payloads elsewhere.
- Sidebar needs only `(team, performance_level)` availability and Header needs only distinct months. Neither reads score, KPI, raw-data, or employee detail.
- The catalog must apply both `filter_records_by_scope` and `filter_records_by_team_levels`; broad team filtering alone would leak the existence of levels outside a manager's explicit assignment.
- Sidebar's existing test mocks the full performance hook and must move to a catalog hook fixture. No dedicated Header test currently mocks this dependency.
- The catalog migration is additive: analytical routes still receive the unchanged full record contract, while the application shell now requests only periods and dimensions.
- Focused catalog tests prove manager team-level filtering and that the endpoint never calls full record loading.
- Team Dashboard invokes the full Insights workspace only as a fallback when its local KPI analysis is empty, then reads only `priority_insights`. It does not consume workspace options, people contribution, KPI trend, team summaries, risks, or driver collections.
- A backward-compatible `view=priority` Insights response can therefore reduce this active fallback payload without changing the default full Insights page contract. The query cache key must include the view to prevent a compact response from satisfying a full-page request.
- `view=priority` is now explicit in both URL and TanStack Query key. The default `view=full` URL and schema remain unchanged for Insights and Planning consumers.
- The compact model is copied rather than mutated, and tests prove full workspace collections remain intact.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Derive endpoint inventory from both FastAPI OpenAPI and static frontend API call sites | Neither source alone proves active compatibility. |
| Instrument queries in a controlled local process/session | Avoid production load and obtain reproducible query counts/timing. |
| Retain bearer authentication for now | The user prohibited speculative auth migration; current design must first be security-tested and measured. |
| Separate measured facts from recommendations and implementation | Prevent speculative performance claims. |
| Treat production hardening as the first implementation release | It closes concrete security and session risks without changing KPI business behaviour. |
| Preserve existing endpoints while adding opt-in summary/detail behaviour | This avoids a breaking response-contract migration for active frontend consumers. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Combined full reads of large backend service/router files were truncated | Continue with targeted symbol searches and bounded line-range inspection. |
| Combined TestClient baseline exceeded the command timeout | Collect endpoint latency and SQL query evidence in smaller independent probes so a single slow flow cannot invalidate the entire baseline. |
| An environment search included a missing `Backend/.env.example` path and returned exit code 1 after useful matches | Treat the missing optional path as non-blocking and use the existing `DevOps/.env.example` plus runtime files for exact-variable verification. |
| A nested-backend `git ls-files ../DevOps/...` check failed because DevOps is outside the Backend submodule | Run ownership/tracking checks from the root repository instead; no files were changed. |

## Resources
- `D:\Projects\PMS_Dashboard\Backend`
- `D:\Projects\PMS_Dashboard\Frontend`
- `D:\Projects\PMS_Dashboard\DevOps`
- User request: `C:\Users\sghd70204\.codex\attachments\be6a1fca-8e0b-49a1-8fc0-1902f2a40636\pasted-text.txt`
- Backend entrypoint: `D:\Projects\PMS_Dashboard\Backend\app.py`
- Frontend entrypoints: `D:\Projects\PMS_Dashboard\Frontend\src\main.tsx`, `D:\Projects\PMS_Dashboard\Frontend\src\App.tsx`

## Visual/Browser Findings
- Targeted Chromium release verification passed six responsive layout, navigation, route-overflow, dialog-accessibility, and serious accessibility checks.
## Phase 9 — runtime reliability audit

- `services/auth_service.py` and `services/cache_service.py` both construct a Redis client and call `PING` at import time. When Redis is unavailable this adds duplicate startup delay and duplicate warnings.
- Authentication already degrades safely to signed-JWT validation when Redis is unavailable; performance caching already has a bounded in-process fallback. A shared lazy provider can therefore remove startup coupling without changing user-visible contracts.
- Socket.IO presence is process-local (`connected_clients`) and the server is created unconditionally whenever the optional package exists. This is suitable for the current local single-process mode, but it must be explicitly disabled on serverless production rather than presented as durable multi-instance realtime.
- Error middleware already creates a request ID and preserves a structured 500 response, but successful responses do not expose the request ID and there is no `Server-Timing` or response payload-size instrumentation.
- Redis is consumed through module-level `redis_client` imports in authentication, RBAC, bulk operations, cache invalidation, monitoring, health, and query optimization. Keeping that public name as a shared lazy proxy avoids a risky cross-cutting API rewrite and preserves existing test patch points.
- The request-timing middleware currently sits inside authentication, so rejected requests are not measured. Moving timing/instrumentation into the outer error middleware will cover authenticated, rejected, and failed requests consistently.
- Existing Socket.IO state is in-process only. The safe compatibility path is an explicit `PMS_REALTIME_MODE=disabled|in_process`, defaulting to `disabled` on Vercel and retaining `in_process` locally.
- The shared lazy Redis proxy passed focused cache, monitoring, runtime-validation, and provider tests (32/32). Importing `app` no longer emitted either of the duplicate Redis timeout warnings; Redis is first touched only by a feature that needs it.
- Request instrumentation now covers successful responses and middleware-generated rejections through the outer error middleware, with `X-Request-ID`, `Server-Timing`, and `X-Response-Time-Ms` headers while keeping existing JSON bodies backward-compatible.
- Production realtime is now explicit end to end: the backend supports `disabled|in_process`, Vercel defaults to disabled, and the static frontend will not start Socket.IO in production unless `VITE_REALTIME_ENABLED=true`.
- Structured file logs now retain normalized route, method, status, duration, and response bytes. Console logs include the same request summary; CORS exposes the diagnostic timing/request headers to approved frontend origins.
- Before final measurement, the listener was identified as a pre-catalog/pre-priority process; it was subsequently restarted onto the final source and revalidated.
- Final warm local HTTP measurements on the restarted current server (five serial samples each):
  - June Performance: 103.90 ms p50, 597,829 bytes, 186 records.
  - Performance catalog: 25.66 ms p50, 2,411 bytes, 6 periods and 21 authorized scopes.
  - Full Insights: 532.89 ms p50, 487,435 bytes.
  - Priority Insights: 508.21 ms p50, 18,838 bytes, capped at 10 priority items with unused analysis collections omitted.
- The catalog reduces the global-shell payload by 99.6% versus June Performance and is 75.3% faster at p50 in this local run. The priority Insights view reduces bytes by 96.1%; generation time only improves 4.6% because the service still computes the full workspace before applying the backward-compatible projection.
- Every measured response carried both `X-Request-ID` and `Server-Timing`.
- Warm in-process SQL instrumentation counted 9 statements for June Performance versus 5 for the catalog. Full and priority Insights each execute 14 statements, confirming that `view=priority` is currently a response-size optimization rather than a query/computation shortcut.
- A priority-only service path now omits response work not consumed by Team Dashboard while preserving exact compact output. Its five-sample live p50 (511.97 ms) was not materially better than the prior 508.21 ms run, so no CPU/latency improvement is claimed; the verified benefit remains the 96.1% payload reduction.
- Canonical API errors are additive and backward compatible: all handled HTTP/validation errors retain `detail` and now also include `success=false`, `message`, and `request_id`. Middleware-generated auth and unhandled-error responses expose the same fields.
- Configuration-name audit found no stale `JWT_SECRET_KEY` deployment use. `CORS_ORIGINS` remains only the internal parsed settings attribute/tests; the external runtime input is consistently `CORS_ALLOWED_ORIGINS`.
- Local PostgreSQL reports Alembic current = head = `e4a7c1d9b520`. No application change in this roadmap requires DDL or a data backfill.
- Final code review found and corrected two observability defects before release:
  - unhandled 5xx errors were counted once inside `ErrorTracker.log_error` and a second time by the refactored middleware;
  - only the base `/health` path was excluded from rate metrics, not liveness/readiness.
- Import-time `DATA_DIR` creation was also removed. Writers already create their required parent directory at the actual write boundary, so read-only/serverless imports no longer attempt this filesystem mutation.
- The last log-safety review found that requests rejected before route resolution fell back to the raw URL path, which could contain an employee ID. Telemetry and persisted error endpoints now use the normalized route template when available and the literal `unmatched` otherwise.
