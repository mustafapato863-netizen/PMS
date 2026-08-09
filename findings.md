# Findings & Decisions

## 2026-08-09 - Hostinger VPS monorepo migration

- The root repository currently tracks `Backend` and `Frontend` as gitlinks/submodules, while `DevOps` is a normal directory.
- The stable parent commit points to Backend `77c988cd137eba1e80583dfa55010238aa191c26` and Frontend `ba64afe171e78c07fcdd07e2a7e583cee501e30c`.
- The intended runtime remains separate services: React/Vite static frontend, FastAPI/Socket.IO backend, Supabase PostgreSQL, and optional Redis behind Nginx.
- Hostinger Web/Cloud hosting is insufficient for the Python backend; the user confirmed a Hostinger VPS is available, so Docker Compose deployment is viable.
- Production deployment must preserve the existing backend authorization/calculation path and keep database and JWT secrets out of Git and frontend bundles.
- Exact import verification: Backend tree contained 278 tracked files and Frontend contained 357; the monorepo conversion staged and committed exactly those counts, with only `.gitmodules` and the two old gitlinks removed.
- The existing `DevOps/compose/docker-compose.prod.yml` resolves `../Backend` relative to `DevOps/compose`, so its build context is invalid. It also mounts an empty Nginx static root, maps port 443 without certificate files, and publishes Prometheus/Grafana directly.
- The current frontend production fallback is hard-coded to the legacy Vercel backend. A same-origin VPS deployment needs the production fallback to use the browser origin, with `/api` and `/socket.io` reverse-proxied to FastAPI.
- The official current Hostinger action is `hostinger/deploy-on-vps@v2`; the older `deploy-action@v1`/personal-token configuration is not the current interface.
- A Docker `internal` network cannot provide backend outbound access to Supabase. Production keeps Redis on the internal network and gives backend/migrations a separate unexposed egress network.
- The old backend migration helper embedded a Supabase credential. Current source now requires `LOCAL_DATABASE_URL` and `REMOTE_DATABASE_URL`; the exposed credential must be rotated outside the repository.
- Connecting the child histories would carry that old credential into the unified repository. The final branch must be squashed directly onto the stable root commit so only the sanitized source snapshot is published.
- The backend image runs as a non-root user and must use stdout logging by default; otherwise `setup_logging()` attempts to create `/app/logs` and fails during startup.


## Requirements
- Audit frontend/backend API compatibility and backend/PostgreSQL compatibility.
- Measure current latency, query count/time, payload size, request count, rendering, cold/warm behaviour, and representative major flows.
- Identify duplicate calls, N+1 queries, slow SQL, missing justified indexes, payload waste, and unsafe serverless assumptions.
- Preserve authentication, authorisation, team/performance-level isolation, reporting periods, configuration versions, KPI formulas, and grade mappings.
- Add only measured, scoped, reversible optimisations with documented invalidation and rollback.
- Produce the ten requested audit, architecture, baseline, results, environment, rollback, and final-report documents.
- Implement the accepted recommendations in staged, release-safe increments, beginning with production configuration security, session cache isolation, and the verified Pharmacy fixture mismatch.

## Global KPI cap normalization (2026-08-03)
- The repository initially contained mixed team-level `capping` declarations: some teams were `uncapped`, while others were `capped_at_100`.
- The user confirmed that the business rule is global: each KPI achievement must display and score at no more than 100%.
- KPI achievement capping and final weighted-score capping are separate concerns. Both are now aligned so a capped KPI cannot leak an above-target achievement through persisted records, API responses, frontend aggregates, or history views.
- The configuration loader applies the global cap to every flat, level-scoped, and position-scoped KPI, protecting older files and uploaded configurations even before the checked-in JSON is updated.
- Legacy database evidence is normalized on read; score and grade are recomputed only when measured canonical KPI contributions exist, preserving a persisted score when a legacy payload has no usable scoring evidence.
- The frontend treats cap metadata as compatibility information rather than an opt-out: achievement is always clamped to `0..100`, and contribution is clamped to the configured weight share.
- All checked-in team JSON files now use `capped_at_100` where capping is declared and no file retains an `uncapped` or `cap_achievement: false` entry.
- Full verification passed: Backend 560 tests; Frontend 194 tests; frontend typecheck/lint/build/budget; graphify update; whitespace checks.
- Balanced Scorecard management analysis remains a separate contract: its `raw_achievement_ratio` is retained for diagnostic comparison, while its weighted contribution and final score remain capped. The global 100% rule applies to operational KPI cards, scores, exports, API serializers, and team analysis.

## OP Final team merge and branch filtering (2026-08-03)
- The requested canonical display identity is `Pre-Approvals OP Final`; the existing Dubai and SHJ/AJM sources must remain distinguishable by normalized branch/region metadata.
- Multi-select branch filtering must be applied before KPI aggregation and employee lists are built; an empty selection means all authorized branches, not no data.
- The deferred analysis step is the per-KPI regional root-cause attribution; this session should not add new attribution narratives or rankings.

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
- The prior post-cache reference values for the endpoints being optimized are Planning options 1,985.53 ms / 20,274 bytes and Reports options 1,486…2422 tokens truncated…7,829 bytes, 186 records.
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

## Performance+ Planning — 2026-08-01

- The repository already contains a completed performance/compatibility audit, reproducible baseline, database query audit, cache architecture, and final implementation evidence.
- The new roadmap will extend those results rather than proposing a rewrite or repeating completed projection/configuration-cache work.
- Current production build evidence: charts 392.53 kB raw / 112.70 kB gzip; vendor 221.08 / 71.04; Team Dashboard 185.67 / 48.73; animation 132.20 / 43.28; Socket.IO 41.18 / 12.86; CSS 244.91 / 35.37.
- Core React/Vite/TypeScript/Tailwind and FastAPI/SQLAlchemy/PostgreSQL choices remain appropriate. Highest-value candidates are selective chart/animation loading, serverless realtime alignment, heavy report/import isolation, response/query budgets, and RTL design-system standardisation.
- The current screenshot's unused space and icon/text crowding are layout-system defects, not evidence that React, Tailwind, or Lucide must be replaced.
- Existing measured work already reduced Planning options by 93.9%, Report options by 95.1%, shell payload by 99.6%, and priority Insights payload by 96.1%; these are baselines, not future roadmap items.
- Remaining measured backend opportunities are full Performance (~598 kB), full Insights (~487 kB), priority Insights retaining 14 SQL statements, and one active-user database query for every protected request.
- SQL accounted for under 9% of the original slow request wall time, so speculative indexes are explicitly excluded until production-like evidence exists.
- Missing evidence that must become Phase 0 of Performance+: browser Core Web Vitals, production cold starts, production p95/p99, DB pool saturation, report/import timings, and Supabase network latency.
- Existing release verification is strong (538 backend tests, 187 frontend tests, production build, type/lint, and six Chromium smoke/accessibility checks); the new plan should preserve these as non-regression gates.
- The safest contract strategy is additive: introduce explicit compact views, migrate internal consumers, observe compatibility, and only then consider changing a default.
- Infrastructure choices, schema-backed jobs, staging mutation/load tests, and production canary each require a separate approval checkpoint.
- Implementation kickoff confirms the existing working tree has unrelated dirty work in the Backend and Frontend submodules; it must be preserved.
- `framer-motion` is imported by the shared `App.tsx` shell and many authenticated screens, so removing it globally is not a safe first patch; component-level lazy loading/CSS replacement must be incremental.
- Existing frontend hooks already expose `usePerformanceData`, `usePerformanceCatalog`, and `useInsightsWorkspace`; implementation should extend these contracts rather than create parallel data clients.
- The existing `priority_only` Insights path preserves priority ordering through a regression test, but still performs full current/previous record loading and several analyses before returning its compact response; this is the safest measured backend target.
- The repository path for the SQL performance adapter must be discovered from imports before editing; an assumed `Backend/repositories/sql_performance_repository.py` path does not exist.
- Removing only the `AnimatePresence` import from `App.tsx` did not change the generated chunk sizes because shared `Header`, `Sidebar`, `WorkspaceLoader`, and other shell components still import Framer Motion; that experiment was reverted to avoid a behavior-only change without a measured gain.
- The first measured safe frontend gate is therefore bundle-budget enforcement, not a partial animation-library removal.
- `ManagementBSCService.list_analysis_records()` loads all management snapshots/configurations and builds records in Python; a future period-scoped priority loader can reduce this, but it requires careful handling of current/previous periods and management configuration continuity.
- `TeamChartsSection` is imported synchronously by `TeamDashboardView` even though charts are below the first viewport; component-level lazy loading is a safe next frontend improvement and can reduce the route's initial work without changing chart behavior.
- After lazy-loading `TeamChartsSection`, the Team Dashboard route fell from 185.67 kB raw / 48.73 kB gzip to 183.88 / 48.13; the chart module is now emitted separately at 2.68 / 1.15 and remains under the bundle budgets.
- Full backend regression reached 540 passed and one failure in an unrelated date-sensitive report-story test: the fixture due date is July 31, 2026 and the current date is August 1, 2026, so `Overdue` is the correct runtime result. This is not on the modified performance paths.
- Full frontend regression passed 55 files / 189 tests with one worker and a 15-second test timeout.
- A combined root/submodule diff inspection timed out due to the dirty nested repositories; this is an inspection-time issue only and does not affect test results.
- The first implementation release now has a passing bundle budget: charts 383.33 kB raw / 108.99 kB gzip, animation 129.11 / 41.82, Team Dashboard 181.33 / 47.17; all are below their enforced limits.
- Priority-only planning classification is covered by a regression test and the focused Insights suite passes 19 tests; no business-value comparison failed.

## Pre-Approvals IP Elective Dubai onboarding — 2026-08-03

- The supplied tables define two mutually exclusive employee workstreams: `IP Elective` uses `Approval Within 48 HR` with a 75% target, while `ER / IP Approval` uses `Approval Within 1.5 HR` with a 100% target.
- Workstream selection is deterministic from exactly one populated turnaround numerator. A row with both or neither populated cannot be scored safely and must fail with the employee identifiers instead of guessing.
- The ER table contains a wording inconsistency: its target header says “within 48 hrs” while the KPI, numerator, and requested logic are 1.5 hours. The canonical configuration uses 1.5 hours and records the correction.
- The supplied formulas do not define an achievement or final-score cap. The new configuration therefore preserves uncapped achievement and weighted contribution; any presentation-only cap must not mutate stored scoring.
- Exclusions are `Leave`, `New Staff`, and `-` in the status/grade fields. `Resigned` is not excluded because it was not supplied as a rule.
- The actual `.xlsx` workbook was not attached, so exact header spelling/order and representative missing-value behavior remain a release-input validation item.

## PMS_Trend_All.xlsx validation — 2026-08-03

- Workbook inspection is intentionally metadata-only: report sheet names, headers, counts, and normalized value categories, never employee names or IDs.
- The source workbook must be compared against the canonical normalized headers used by `preapprovals_ip_elective_dubai.py`; any aliases will be handled in the cleaner rather than by changing the business formulas.
- The target sheet has a merged KPI reference area in columns Y:AE and 511 formatted rows, but only 42 non-empty data rows. The actual employee header is row 2, not row 1.
- The source combines the two turnaround fields into `Approval Within 48 HR/1.5 HR` and `A.Number Approval within 48 HR/1.5 HR`; it does not provide separate 48-hour and 1.5-hour columns.
- The production target sheet has 41 non-empty data rows across January–June 2026; one `Leave` row is excluded, leaving 40 scored rows. Its target pairs are `(3%,75%)`, `(1%,100%)`, `(3%,100%)`, and `(6%,75%)`; the turnaround component separates the workstreams and the rejection component validates historical target revisions.
- Recomputing the 40 source performance scores from raw counts and row-level targets matches the workbook within floating-point noise (maximum absolute difference `2.3e-16` in fraction scale).

## Updated target-pair validation — 2026-08-03

- The user supplied a refreshed workbook with target-pair logic and calculation formulas; no mapping change is assumed until the pair values and formulas are inspected.

### Confirmed target-pair rules

- The refreshed target sheet contains four observed pairs: `(0.03, 0.75)`, `(0.06, 0.75)`, `(0.01, 1.0)`, and `(0.03, 1.0)`.
- `(3%,75%)` and `(6%,75%)` classify as `IP Elective`; `(1%,100%)` and `(3%,100%)` classify as `ER / IP Approval`. The rejection target is historically revised, so using only the turnaround target would lose validation of the first target column.
- The sheet now includes formula columns: `A.IP/ER Initial Rejection %`, `A.Number Approval within 48 HR/1.5 HR`, `Rejection Rate`, `% of Submission Within Due date`, and `Performance Score`. The cleaner continues to recompute these from raw counts and row-level targets, then validates against the workbook formulas rather than trusting cached Excel values.
- The pair-aware cleaner and config now reject missing or unsupported target pairs. The complete workbook dry-run passed with `1,028` records, `245` employees, no failed teams, and `40` active rows from the new sheet (`13` IP Elective / `27` ER / IP Approval).
- Direct score reconciliation against the refreshed workbook matched all `40` active new-team rows exactly (`max_diff = 0.0` in fraction scale). Full Backend regression passed `550` tests; graphify was refreshed to `6,100` nodes.

## Session: 2026-08-03 - Pre-Approvals OP Final SHJ/AJM onboarding

### Implementation discoveries

- `ExcelProcessor` and `SeedingService` use explicit per-sheet cleaner/mapping registrations; the new sheet must be added in both places and included in the UAE region fallback list.
- The seeding path sends Employee rows with a position through the configurable multi-team scorer, so the single KPI set is isolated under the internal `OP Final` position while SHJ/AJM remains one user-facing team.
- The shared KPI service currently treats missing actual values as zero and has no conditional exception hook. The supplied `"-"` TAT rule therefore needs an explicit, config-driven exception that returns the Initial Rejection achievement as the final score.
- The workbook's active rows use `Submitted Requests` as the rejection denominator and `Submitted Requests - Manual Request` as the TAT denominator; the cleaner will preserve the row-level targets and expose canonical columns for both ratios.
- The real workbook contains 23 scored rows after excluding one Leave row (14 AJM and 9 SHJ); all current rows have a usable TAT value.
- Recalculation of all 23 workbook scores matched the cached `Performance Score` values with a maximum absolute difference of `2.22e-16` on the decimal scale.
- The missing-TAT exception is covered with a synthetic `"-"` row and returns the Initial Rejection achievement directly (not weighted a second time).

## Session: 2026-08-03 - Pre-Approvals IP SHJ/AJM onboarding

- Requested sheet: `Pre-Approvals IP Final SHJAJM`; the workbook path is `D:\Trend\PMS_Trend_All.xlsx`.
- The sheet uses row 1 as the employee header and stores the KPI reference table starting at column S; the employee data columns are `Assigned Request`, `Approved Requests`, `Rejected Requests`, and `Submitted Within Month (Untill 3rd of next month)`.
- The source has two branch values (`SHJ` and `AJM`) in its `Team` column and the supplied formula is a single 40% Acceptance / 60% Submission Within Month scorecard.
- Both source targets are currently 1.0 (100%) and the workbook formulas use the 80% baseline in both achievement formulas; source scores must be reconciled from the raw counters and row-level targets rather than cached Excel formulas.
- The sheet contains four active rows (two SHJ and two AJM), no excluded rows, and one target pair `(1.0, 1.0)`.
- Recomputing `(acceptance - 0.80) / (target - 0.80)` and `(submission - 0.80) / (target - 0.80)` with 40%/60% weights matches all four cached Performance Scores exactly (`max_diff = 0.0`).
- The new cleaner exposes canonical counters/ratios and an internal `IP Final` position so the existing configurable scorer is used without presenting SHJ/AJM as separate teams.
- The scorecard intentionally preserves uncapped upside and floors below-baseline achievement at zero, matching the existing IP Final implementation; the current source rows are all above the baseline.
- Focused tests cover registration, counter-based ratios, baseline scoring, and active-row-only dry-run import. Full workbook dry-run now includes both new SHJAJM sheets with no failed teams.

- Requested sheet name: `Pre-Approvals OP Final SHJAJM`.
- Supplied KPI model: Initial Rejection 60% (lower is better) plus Submission Within TAT 40% (higher is better).
- Exception rule: when Submission Within TAT is unavailable (`-`), final score equals Initial Rejection achievement expressed as a percentage.
- Workbook inspection and compatibility mapping are complete; the production sheet uses the row-1 header and the supplied denominators/targets.
## 2026-08-03 — OP Final SHJ/AJM dashboard score mismatch

- The screenshot's KPI cards are internally plausible: Initial Rejection 2.2% against a 5% lower-is-better target produces a capped 60% contribution, while Submission Within TAT 95.4% against 70% produces an uncapped 54.5% contribution. The weighted raw total is therefore about 114.5 points (or 100 after the configured overall cap), not 1.1%.
- The dashboard's `TeamDashboardView` intentionally replaces the canonical pooled score with the hook's employee-score average unless the two values differ by no more than 15 points (`calculatedAvgScore` and `trendData`). This is unsafe for legacy records whose persisted `evaluation.score` is stored as a decimal ratio (for example 1.1 for 110%) or stale percent value. In that case the canonical KPI aggregate is rejected and the stale 1.1 value is rendered.
- `useTeamData` and `resolveDisplayScore` also trust `evaluation.score` before deriving a score from KPI values for this team. That explains the 1.1% average, all agents classified as E, and top/bottom scores around 1.1% while the cards display correct KPI contributions.
- The backend dashboard resolver normalizes KPI values but only has explicit score reconciliation for the legacy IP Elective team (and Sales); OP Final SHJ/AJM falls through to `item.score`, so old/mis-scaled persisted scores remain visible even when canonical `kpi_values` are correct.
- Local JSON June records are correctly persisted at 100.0 for this team, so the shown mismatch is most consistent with stale/mis-scaled production records or an older backend deployment/data path rather than the OP Final formula itself. No database writes were performed during this diagnosis.

## 2026-08-03 — OP Final cap correction implemented

- Both OP Final SHJ/AJM KPI definitions now cap achievement at 100%; the final score is also capped at 100%.
- The scoring service now persists the effective capped ratio for explicitly capped KPIs, while intentionally uncapped teams retain their existing above-target evidence.
- The dashboard resolver now normalizes legacy KPI values and recalculates score/grade from capped contributions for capped configurations, so old rows no longer expose 110%+ as a team or KPI score.

## 2026-08-03 - OP Final branch merge findings

- The two OP Final sources must keep separate configs because Dubai is position/workstream scoped while SHJ/AJM uses its own 60/40 KPI set; merging the JSON configs would change scoring semantics.
- A presentation-level canonical alias is safer than a database migration: source records remain auditable and the repository accepts `Pre-Approvals OP Final` as an alias for both source teams.
- Branch identity is available from the source team/branch fields and is now normalized with fallback checks across `Team`, `Branch`, `Site`, `Area`, and identity region fields.
- Multi-selection is stored as a comma-separated `branches` query value, with legacy `branch`/`location` keys kept synchronized for backward compatibility.
- For the merged view, the headline average is the average of selected employees' display scores; KPI cards continue to use configured KPI aggregation. Region-level KPI attribution/root-cause analysis remains deferred by request.
- Frontend analysis and employee action details consume the cap metadata. Actual KPI values and targets remain unchanged; only achievement and weighted contribution are capped.

## 2026-08-03 - IP Final branch merge findings

- `Pre-Approvals IP Final Dubai` and `Pre-Approvals IP Final SHJAJM` now share the presentation-level identity `Pre-Approvals IP Final`.
- Their source configurations remain position-scoped: Dubai keeps `Combined` (50/30/20), `IP Approval` (60/40), and `IP Discharge` (100%) while SHJ/AJM keeps `IP Final` (40/60). This avoids changing source scoring semantics.
- The merged route reuses authoritative source branch matching and the URL-backed multi-branch selector; employees, headcount, trends, KPI aggregation, and average score follow the selected branch set.
- Backend repository, authorization, and action aliases accept the canonical name while source rows/configs remain auditable. No database migration or source-data rewrite was required.
- Per-KPI branch attribution/root-cause analysis remains deferred as requested.

## 2026-08-04 - UAE Pre-Approvals parent consolidation

- The UAE parent uses route id `pre-approvals-uae` because the legacy `/team/pre-approvals` route belongs to the Egypt IP Offshore team.
- `Pre-Approvals` groups OP Final, IP Final, and IP Elective source teams at the presentation and repository-filter layers; source team values and scoring configs remain unchanged.
- The parent defaults to a workflow summary. Selecting one workflow loads that workflow's own configuration and KPI cards; mixed workflow KPI cards/analysis are intentionally suppressed.
- The existing branch selector remains multi-select and scopes the parent roster, headcount, scores, and trends. Per-KPI regional attribution remains deferred.
- `Pre-Approvals IP Elective Dubai` keeps its database/config identifier but is displayed as `Pre-Approvals IP Elective` in navigation and profile labels.
- Backend team-level authorization now expands parent aliases, and exports accept an optional workflow selector.
- No schema migration, source-data rewrite, or production deployment was made.

## 2026-08-04 - Call Center parent/channel consolidation

- `Inbound` and `Outbound` are now presentation-level children of `Call Center`; source records and channel-specific KPI configurations remain unchanged.
- Channel selection is applied before roster, headcount, trends, KPI aggregation, score analysis, and export resolution. `All Channels` is summary-only so the UI does not imply that distinct channel KPI definitions can be pooled safely.
- Authorization intentionally remains asymmetric: a manager scoped to `Inbound` cannot access `Outbound`, while a manager scoped to `Call Center` can access both. `Inbound UAE` is explicitly excluded.
- No database migration is required because the parent is an application-layer alias over the existing source team values.
