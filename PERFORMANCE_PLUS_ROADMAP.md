# PMS Performance+ Roadmap

Date: 2026-08-01
Scope: Frontend, API, PostgreSQL/Supabase, caching, reports/imports, realtime, deployment, observability, and release quality.
Mode: Planning only. No application, schema, environment, or production change is authorized by this document.

## 1. Outcome

Deliver a faster and more predictable PMS without changing KPI formulas, grades, historical periods, permissions, configuration versions, or PostgreSQL as the source of truth.

The roadmap extends the completed July performance work. It does not repeat already delivered projection, catalog, priority-payload, configuration-cache, Redis-startup, or observability improvements.

## 2. Guardrails

1. Measure before optimizing and record before/after evidence.
2. Preserve role, team, region, level, period, and user isolation.
3. Keep full-detail contracts backward compatible while adding compact or paginated contracts.
4. Add an index only after production-like SQL, cardinality, and `EXPLAIN (ANALYZE, BUFFERS)` evidence.
5. Keep feature flags and a rollback path for every material runtime change.
6. Never run destructive load, upload, report, or migration tests against Production.
7. Do not rewrite React, FastAPI, SQLAlchemy, PostgreSQL, or Tailwind without measured evidence that an incremental fix cannot meet the target.

## 3. Verified starting point

| Area | Current evidence |
|---|---|
| Planning options | 120.71 ms local warm p50; 20,274 bytes |
| Report options | 72.61 ms local warm p50; 33,006 bytes |
| Performance response | 103.90 ms local warm p50; 597,829 bytes; 9 SQL statements |
| Performance catalog | 25.66 ms local warm p50; 2,411 bytes; 5 SQL statements |
| Full Insights | 532.89 ms local warm p50; 487,435 bytes; 14 SQL statements |
| Priority Insights | 511.97 ms local warm p50; 18,838 bytes; still 14 SQL statements |
| Largest frontend chunk | Recharts: 392.53 kB raw / 112.70 kB gzip |
| Animation chunk | Framer Motion: 132.20 kB raw / 43.28 kB gzip |
| Team Dashboard route | 185.67 kB raw / 48.73 kB gzip |
| Verification baseline | 538 backend tests, 187 frontend tests, build/type/lint, and Chromium smoke passed |

These are local warm results, not production p95/p99 claims.

## 4. Performance+ service-level targets

Targets are release gates after a staging baseline confirms the same test fixture and network profile.

### Browser targets

| Metric | Target |
|---|---:|
| LCP | <= 2.5 s at p75 |
| INP | <= 200 ms at p75 |
| CLS | <= 0.10 at p75 |
| Initial authenticated shell JavaScript | <= 250 kB gzip |
| Additional route JavaScript | <= 150 kB gzip for normal routes |
| Main-thread long tasks during route entry | no task > 200 ms in the reference workflow |
| Route transition with warm data | usable content <= 1.0 s at p95 |
| Unexpected document horizontal overflow | zero at supported viewports and 125% zoom |

### API and data targets

| Metric | Target |
|---|---:|
| Normal read endpoints | <= 500 ms p95 |
| Full Insights | <= 900 ms p95 after warm start |
| Priority Insights | <= 350 ms p95 and <= 8 SQL statements |
| Default Performance payload | <= 150 kB through compact summary/pagination |
| Default Insights payload | <= 200 kB; drill-down data loaded on demand |
| API 5xx rate | < 0.2% over a 15-minute release window |
| DB statement time | <= 100 ms p95 for dashboard read paths |
| DB pool wait | <= 100 ms p95 under approved load profile |

### Jobs and reliability targets

| Metric | Target |
|---|---:|
| Upload/report request acknowledgement | <= 300 ms with a job ID |
| Long report/import execution | outside the request lifecycle with progress and retry state |
| Cold-start API response | establish baseline, then reduce by at least 30% or move the affected path to persistent compute |
| Availability | >= 99.9% monthly, excluding planned maintenance |
| Realtime presence | one documented authoritative mode; no process-local presence presented as global state |

## 5. Delivery plan

### Phase 0 — Production-like baseline and budgets

Estimated effort: 3–4 working days.

- Add staging-only Web Vitals collection for LCP, INP, CLS, navigation timing, and route identity without employee data.
- Capture cold/warm API p50/p95/p99, response bytes, SQL count/time, pool wait, and server timing.
- Benchmark Executive, Team, Employee, Insights, Reports, login, upload preview, import, and report generation.
- Add bundle-size and route-chunk budgets to CI.
- Add controlled k6/Locust read profiles for 1, 10, 50, and agreed peak concurrent users.
- Record device/network profiles and test data cardinality so results are reproducible.

Acceptance gate:

- A signed baseline exists for every target metric.
- No employee data, tokens, or raw query strings appear in telemetry.
- CI fails on material bundle, payload, query-count, or latency regression beyond the agreed tolerance.

### Phase 1 — Frontend loading and rendering

Estimated effort: 5–7 working days.

- Keep React, Vite, TypeScript, Tailwind, TanStack Query, Zustand, and Lucide.
- Lazy-load chart features at component level, not only route level.
- Replace small sparklines/progress visuals with lightweight SVG/CSS; keep Recharts for complex charts.
- Replace simple fades, hover transitions, and drawer movement with CSS; keep Framer Motion only where sequencing or gesture behavior justifies it.
- Remove animation imports from the authenticated application shell where possible.
- Audit TanStack Query keys, cancellation, stale times, `select`, placeholder data, and prefetching by route.
- Memoize only measured expensive aggregations; avoid blanket `memo` and callback churn.
- Virtualize or paginate tables only when the rendered row threshold is exceeded.
- Self-host/subset the primary font or preload it with a stable fallback stack.
- Standardize responsive grids, icon wrappers, logical RTL spacing, and content-width tokens.

Acceptance gate:

- Browser targets pass on desktop, 1024/tablet, mobile, and 125% zoom.
- Existing visual/accessibility snapshots remain valid or receive an explicit approved update.
- No chart, filter, keyboard, dialog, or RTL behavior regression.

### Phase 2 — API payload and compute reduction

Estimated effort: 7–10 working days.

- Add an explicit compact Performance summary contract, migrate internal consumers, and change any default only after a compatibility window confirms no external consumer depends on the full response.
- Move employee rows, KPI values, six-month trend, and people contribution to authorized on-demand endpoints.
- Add cursor pagination for large employee/performance lists; preserve export-all as a server-side job.
- Split full Insights into summary, drivers, people, trend, risk, and detail boundaries while keeping the current full contract available during migration.
- Make `view=priority` skip unused queries and analysis rather than only trimming its response.
- Compute repeated configuration mappings and derived KPI metadata once per request.
- Profile serialization and Python aggregation before introducing alternate serializers or vectorized implementations.
- Add ETag/conditional GET only to stable authorized catalog/configuration responses with correct user/scope variation.

Acceptance gate:

- Performance and Insights payload/query targets pass.
- Response compatibility tests prove unchanged business values for the same scope.
- Authorization tests cover cross-team, cross-region, cross-level, inactive-user, and historical-period access.

### Phase 3 — Authentication, cache, and PostgreSQL

Estimated effort: 5–7 working days.

- Measure the active-user lookup cost and cache only the minimal authorization/session record with a short TTL and explicit invalidation on password, status, role, or assignment change.
- Version cache keys by user scope, period, team, level, region, and configuration version where the response depends on them.
- Add stampede protection and TTL jitter for expensive shared aggregates.
- Enable `pg_stat_statements` in an authorized staging/production-like PostgreSQL environment.
- Configure connect, statement, and lock timeouts plus `application_name`.
- Record pool utilization and wait time before changing pool size.
- Review unused/large indexes using production query history; use concurrent migrations with tested downgrade only when evidence supports a change.
- Consider a monthly summary table/materialized view only if measured dynamic aggregation remains over target at realistic scale.

Acceptance gate:

- Cache invalidation tests prove no stale authorization or cross-user leakage.
- Database migration upgrade/downgrade is verified if DDL is introduced.
- Query plans and write overhead are recorded before and after every accepted index/view.

### Phase 4 — Reports, uploads, and heavy Python work

Estimated effort: 7–10 working days.

- Remove Pandas, NumPy, OpenPyXL, and python-pptx imports from normal API startup paths where possible.
- Introduce a persisted job model containing owner, scope, type, state, progress, timestamps, retry count, output reference, and error code.
- Execute report generation and large uploads in a dedicated worker with idempotency and bounded retries.
- Store generated files in object storage with expiring authorized download links, not an ephemeral serverless filesystem.
- Validate uploads before enqueueing; preserve audit history and rollback semantics.
- Add cancellation and safe deletion rules for queued, running, completed, and failed jobs.

Acceptance gate:

- API requests return quickly with a job ID.
- Worker restart does not lose job state or duplicate promoted data.
- Download/deletion permissions and audit records pass E2E tests.

### Phase 5 — Hosting and realtime alignment

Estimated effort: 4–6 working days plus infrastructure approval.

Recommended target architecture:

- Frontend remains on Vercel/CDN.
- Supabase PostgreSQL remains the source of truth.
- FastAPI moves to persistent container compute if durable sockets and background jobs are required.
- Redis is a managed shared service when used for cache, job queue, or pub/sub.
- Supabase Realtime is a valid alternative when presence/database events cover the use case.

Actions:

- Choose one production realtime mode: Supabase Realtime, or Socket.IO on persistent compute.
- Remove production Socket.IO client/server bundles when realtime is disabled.
- Load-test the selected mode with multiple instances and reconnect scenarios.
- Separate REST health from worker and realtime health.
- Document failure behavior when Redis, realtime, worker, or object storage is unavailable.

Acceptance gate:

- Online/offline and last-seen behavior is consistent across instances.
- No Vercel function is treated as a durable socket or background worker.
- Failover behavior is observable and documented.

### Phase 6 — Release gate and controlled rollout

Estimated effort: 4–5 working days.

- Run backend, frontend, type, lint, unit, integration, migration, browser, accessibility, and E2E suites.
- Run load tests only against Local/Staging/UAT with dedicated data.
- Verify roles and scopes using Admin, Manager, and restricted users.
- Deploy behind feature flags: compact Performance, split Insights, auth cache, async reports, and selected realtime mode.
- Canary to a small authorized group; compare performance and error metrics against the prior version.
- Expand only when targets hold for the agreed observation window.
- Keep the prior artifact and environment configuration ready for rollback.

Acceptance gate:

- All functional gates pass.
- Performance targets pass without scoring, permissions, data-integrity, or accessibility regression.
- Rollback rehearsal is completed before full rollout.

## 6. Technology decisions

| Technology | Decision | Boundary |
|---|---|---|
| React + Vite + TypeScript | Keep | Optimize route/component boundaries; no rewrite |
| Tailwind CSS | Keep | Add design tokens and RTL logical-property standards |
| TanStack Query | Keep | Standardize keys, cancellation, cache ownership, and lazy detail |
| Zustand | Keep selectively | Do not move server state into Zustand |
| Lucide | Keep | Standardize icon size/container/alignment |
| Recharts | Keep selectively | Complex charts only; lazy-load and replace tiny visuals |
| Framer Motion | Reduce | CSS for simple motion; retain justified complex interaction |
| Socket.IO | Conditional | Persistent hosting only; otherwise Supabase Realtime or disabled |
| FastAPI + SQLAlchemy | Keep | Avoid a risky full async rewrite without concurrency evidence |
| PostgreSQL/Supabase | Keep | Evidence-driven plans, timeouts, telemetry, and migrations |
| Pandas/NumPy/OpenPyXL/PPTX | Isolate | Worker/import/report paths, not ordinary API cold start |

### Delivery ownership and risk

| Phase | Primary owner | Reviewer | Risk | Rollback boundary |
|---|---|---|---|---|
| 0. Baseline | Full-stack/Platform | Security + QA | Low | Disable staging telemetry and CI budgets |
| 1. Frontend | Frontend | UX + QA | Medium | Route/component feature flags and prior asset artifact |
| 2. API contracts | Backend/Full-stack | Security + Product | High | Keep full endpoints/contracts and revert consumer flags |
| 3. Auth/cache/DB | Backend/DBA | Security | High | Disable cache path; concurrent migration rollback if applicable |
| 4. Jobs | Backend/Platform | Security + QA | High | Keep synchronous path temporarily behind an admin-only flag |
| 5. Hosting/realtime | Platform | Backend + Security | High | DNS/environment rollback to prior API and realtime-disabled mode |
| 6. Rollout | Release owner | Product + QA | Medium | Canary stop and redeploy prior verified artifacts |

## 7. Sequencing and dependencies

```text
Measured staging baseline
        |
        +--> Frontend bundle/rendering
        |
        +--> API compact contracts --> DB/cache tuning
        |
        +--> Async jobs -----------> Hosting/realtime decision
                                      |
                                      v
                         Integrated release gate and canary
```

Phase 0 is mandatory. Phases 1 and 2 can run in parallel after the baseline. Phase 3 depends on Phase 2 query evidence. Phases 4 and 5 share infrastructure decisions and should be released together only after worker/realtime failure modes are tested.

## 8. Estimated programme duration

Assuming one senior full-stack engineer, part-time QA, and timely infrastructure access:

- Minimum release with Phases 0–3: 4–5 weeks.
- Full Performance+ roadmap through async jobs/realtime and canary: 7–9 weeks.
- Add contingency for production access, test-data preparation, and infrastructure approvals.

This is an engineering estimate, not a deadline. Each phase can ship independently after its gate passes.

## 9. Explicit non-goals

- No redesign of KPI formulas, weights, grade thresholds, or business phases.
- No unmeasured database indexes.
- No migration from React to Next.js or from Tailwind to a heavier component suite.
- No wholesale conversion of SQLAlchemy to async.
- No destructive production load test.
- No promise of p95/p99 or Core Web Vitals before production-like telemetry exists.

## 10. First implementation release

Recommended first release scope:

1. Performance telemetry and CI budgets.
2. Component-level chart loading and simple-motion CSS replacement.
3. Compact Performance response with lazy employee/KPI detail.
4. Real priority-Insights query/compute reduction.
5. Staging load and role/scope regression gate.

This scope provides the highest measurable user benefit without requiring a database migration or immediate hosting move.

## 11. Approval checkpoints

Implementation should pause for explicit approval at these boundaries:

1. After Phase 0, approve the measured budgets and peak concurrency profile.
2. Before changing any default API response contract.
3. Before introducing a job table, object storage, managed Redis, or a new hosting service.
4. Before running staging load tests that create uploads or reports.
5. Before canarying production traffic.
