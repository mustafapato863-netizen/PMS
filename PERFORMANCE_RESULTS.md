# Performance Results

Date: 2026-07-29
Environment: local PostgreSQL, serial warm measurements, authorized Admin scope.

## Implemented optimizations

1. Parsed team configuration cache keyed by canonical path, nanosecond mtime, and file size.
2. Per-request configuration reuse for dashboard record mapping.
3. SQL scalar projections for Planning, Reports, and global shell option discovery.
4. Authorized `/api/performance/catalog` endpoint for shell periods/team-level scopes.
5. Backward-compatible `view=priority` Insights response for Team Dashboard.
6. Lazy people-contribution and six-month KPI trend analysis only when one KPI is selected.

No KPI formula, grade mapping, historical period, authorization rule, or database schema was changed.

## Results

### Configuration-cache stage

| Flow | Baseline p50 ms | Cached p50 ms | Change | Payload |
|---|---:|---:|---:|---:|
| Performance June 2026 | 943.42 | 367.15 | -61.1% | 597,829 bytes |
| Planning options | 5,007.43 | 1,985.53 | -60.4% | 20,274 bytes |
| Report options | 3,370.72 | 1,486.04 | -55.9% | 33,006 bytes |
| Insights June 2026 | 6,989.40 | 1,647.02 | -76.4% | 487,435 bytes |

Complete response bytes and SHA-256 hashes remained identical for these compatibility checks.

### Projection and payload stage

| Flow | Reference p50 ms | Final p50 ms | Change | Final payload |
|---|---:|---:|---:|---:|
| Planning options | 1,985.53 | 120.71 | -93.9% | 20,274 bytes |
| Report options | 1,486.04 | 72.61 | -95.1% | 33,006 bytes |
| Performance June 2026 | N/A | 103.90 | N/A | 597,829 bytes |
| Performance catalog | N/A | 25.66 | N/A | 2,411 bytes |
| Full Insights | N/A | 532.89 | N/A | 487,435 bytes |
| Priority Insights | N/A | 511.97 | N/A | 18,838 bytes |

The catalog is 99.6% smaller than the June Performance response and was 75.3% faster at p50 in the final local run. Priority Insights is 96.1% smaller than full Insights. Its latency did not improve materially, so no CPU/latency gain is claimed for that view.

### SQL evidence

| Flow | Warm SQL statements |
|---|---:|
| Performance June 2026 | 9 |
| Performance catalog | 5 |
| Full Insights | 14 |
| Priority Insights | 14 |

Planning statements fell from 16 to 8; Report options fell from 12 to 6. Priority Insights currently retains the same core query workload as full Insights.

## Runtime reliability evidence

- Redis performs no network operation during module import.
- The first Redis-dependent action uses a 0.25-second timeout and 30-second retry cooldown by default.
- Every measured response included `X-Request-ID` and `Server-Timing`.
- Successful, authorization, validation, and server errors use an additive canonical error envelope while retaining the legacy `detail` field.
- Vercel defaults realtime to disabled; local/single-process hosting can explicitly use `in_process`.

## Final verification

| Check | Result |
|---|---|
| Full backend suite | 538 passed |
| Full frontend suite | 55 files, 187 passed |
| Frontend type check | passed |
| Frontend lint | passed |
| Frontend production build | passed; 3,298 modules |
| Targeted Chromium E2E/accessibility | 6 passed |
| Focused projection/Insights/runtime tests | passed |
| Compile checks | passed for application packages/files |
| Git whitespace check | passed |
| Alembic current/head | `e4a7c1d9b520` / `e4a7c1d9b520` |
| New database migration | none |

The test environment still emits dependency deprecation warnings and cannot write `.pytest_cache`; neither affected test results or application compilation.

## Remaining measured opportunities

1. Full Performance and full Insights remain approximately 598 kB and 487 kB.
2. Priority Insights reduces transfer size but still performs the core 14-query analysis.
3. Browser Web Vitals, production cold starts, DB-pool saturation, and production p95/p99 require staging/production telemetry.
4. Authentication still performs an active-user database lookup per protected request.
