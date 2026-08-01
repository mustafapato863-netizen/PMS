# Task Plan: PMS Production Hardening and Performance Implementation

## Goal
Implement the accepted audit recommendations in safe, reversible stages while preserving security, business rules, historical periods, configuration versions, and PostgreSQL as the source of truth.

## Current Phase
Complete — all accepted implementation phases and release checks are finished.

## Phases

### Phase 1: Current-State Architecture Audit
- [x] Inventory runtime architecture, repositories, deployment, and active entrypoints
- [x] Map frontend requests to backend routes and schemas
- [x] Audit database schema, migration graph, relationships, indexes, and query paths
- [x] Trace authentication, upload, dashboard, reporting, cache, and Vercel flows
- [x] Produce `PERFORMANCE_AND_COMPATIBILITY_CURRENT_STATE_AUDIT.md`
- **Status:** completed

### Phase 2: Reproducible Performance Baseline
- [x] Define safe representative local dataset and authenticated test scope
- [x] Measure API latency, payload size, and query count/time
- [x] Measure the reproducible frontend build baseline; document unavailable browser/cold-start evidence
- [x] Record exact commands, environment, limitations, and raw evidence
- [x] Produce `PERFORMANCE_BASELINE.md`
- **Status:** completed

### Phase 3: Compatibility and Database Evidence
- [x] Build active API compatibility matrix from frontend usage and OpenAPI
- [x] Identify response/type/nullability/scale/error mismatches
- [x] Capture database query and index evidence with EXPLAIN/EXPLAIN ANALYZE
- [x] Produce `API_COMPATIBILITY_MATRIX.md` and `DATABASE_QUERY_AND_INDEX_AUDIT.md`
- **Status:** completed

### Phase 4: Evidence-Backed Optimisation
- [x] Rank findings by risk and measurable impact
- [x] Implement the smallest safe measured configuration-loading improvement
- [x] Add no migration because execution plans did not justify one
- [x] Document cache architecture and invalidation
- **Status:** completed

### Phase 5: Production, Security, and Vercel Verification
- [x] Decide authentication/cookie approach from actual runtime design
- [x] Validate connection management, filesystem usage, Redis fallback, CORS, and environment requirements
- [x] Produce cache, auth, production, and rollback documents
- **Status:** completed

### Phase 6: Regression and Performance Results
- [x] Run focused, contract, frontend and backend verification; record known existing failures
- [x] Compare before/after metrics and response hashes
- [x] Produce `PERFORMANCE_RESULTS.md` and `FINAL_IMPLEMENTATION_REPORT.md`
- **Status:** completed

### Phase 7: Critical Production Hardening
- [x] Fail production startup when the JWT secret or PostgreSQL URL is missing or unsafe
- [x] Prevent automatic production seeding
- [x] Align production environment documentation with runtime variable names
- [x] Cancel and clear user-scoped frontend queries on logout and terminal authentication failure
- [x] Update Pharmacy capping test fixtures to the current configured KPI input
- [x] Run focused and full regression checks
- **Status:** completed

### Phase 8: Scoped Query and Payload Optimisation
- [x] Audit authorisation dimensions before moving option discovery to SQL projections
- [x] Add projection-based option queries without weakening team, level, or region scope
- [x] Add backward-compatible summary/detail controls only where active consumers permit them
- [x] Keep expensive KPI people/trend analysis lazy and separately requested where practical
- [x] Measure response size, latency, query count, and compatibility before and after
- **Status:** completed

### Phase 9: Runtime Reliability and Observability
- [x] Remove synchronous Redis network work from module import paths
- [x] Document and enforce supported realtime operating modes
- [x] Add request ID, server timing, payload-size, and normalized route telemetry without sensitive data
- [x] Introduce a backward-compatible canonical API error shape
- **Status:** completed

### Phase 10: Configuration Source of Truth and Release Gate
- [x] Remove remaining environment-name and configuration-version ambiguity
- [x] Run backend, frontend, type, build, and targeted browser verification
- [x] Update implementation, rollback, performance, and production requirement reports
- [x] Review the final diff for business-rule, security, and compatibility regressions
- **Status:** completed

## Key Questions
1. Which frontend requests are active in routed production pages, and do they match OpenAPI and actual response schemas?
2. Which major flows have measured duplicate requests, N+1 queries, large payloads, or Python-side work that materially increases latency?
3. Which caches already exist, what are their scope and invalidation rules, and are they safe for serverless/team-isolated use?
4. What database and migration URLs, connection limits, and production domains are actually configured?
5. Which improvements can be proven without changing KPI, grade, period, or configuration-version semantics?

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Audit and baseline before code changes | The request explicitly prohibits speculative optimisation and requires before/after evidence. |
| Use the current local PostgreSQL environment for non-destructive baseline work | It is the currently verified safe environment; production load/destructive testing is prohibited. |
| Preserve all unrelated dirty worktree changes | The repository contains prior user work that must not be overwritten or reformatted. |
| Implement in release-sized phases starting with P0 controls | The accepted roadmap crosses frontend, backend, runtime, and API contracts; sequencing limits regression blast radius. |
| Fix Pharmacy fixtures, not KPI calculations | The current configuration requires `NoofPrescriptionAch%`; the failing fixtures are stale while scoring semantics are authoritative. |
| Keep response-contract changes backward compatible | Existing production consumers must continue to work while summary/detail paths are introduced. |
| Keep full Performance and Insights as the default contracts | Active detailed consumers still require raw records and complete analysis; compact endpoints/views are explicit. |
| Do not add a database migration | Current/head match, projections use existing relations, and no measured problem requires DDL. |
| Disable realtime by default on serverless production | Presence is process-local and cannot be represented as durable multi-instance delivery. |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| Combined full reads of large backend routers/services exceeded output context | 1 | Switched to targeted symbol searches and bounded line-range reads; no production files were changed. |
| Combined in-process TestClient baseline for 11 endpoints exceeded the 120-second command limit | 1 | Split the baseline into bounded per-endpoint HTTP measurements and focused query-count probes. |
| Relation-size inventory query used an ambiguous `oid` column | 1 | Qualify the relation identifier as `c.oid` on the next inventory pass. |
| Focused pytest command referenced a non-existent `tests/test_config_loader.py` | 1 | Re-run only the new cache test module and existing discovered configuration tests. |
| Ruff is not installed in the backend virtual environment | 1 | Use the repository's available compile/test checks and report lint as unavailable. |
| CIM process inspection exceeded its 10-second bound | 1 | Use bounded listener/process commands without expensive CIM enumeration. |
| `wmic` is unavailable on this Windows installation | 1 | Resolve the listener with `netstat` and inspect the exact PID with `Get-Process`. |
| Broad regression command referenced absent `test_insights_api.py`, `test_planning_api.py`, and `test_reports_api.py` modules | 1 | Discover the actual repository test filenames before re-running the suite. |
| Full frontend test run had 8 five-second timeouts while backend tests and database inventory ran concurrently | 1 | Re-run frontend tests with one worker and a bounded 15-second test timeout to distinguish contention from defects. |
| Full serial frontend suite exceeded the five-minute command limit without producing a terminal result | 1 | Run only the six previously failing test files in isolation and report the full-suite timeout separately. |
| Full backend suite has 3 Pharmacy capping failures | 1 | Confirmed the tests provide legacy prescription columns while the current config requires `NoofPrescriptionAch%`; left business logic/config unchanged and reported the existing mismatch. |
| Full frontend suite has one default five-second timeout | 2 | The same test passes in the isolated 25-test run with a 15-second bound; reported as timing flakiness. |
| Initial parallel skill-file read was truncated by output context | 1 | Re-read each selected skill separately with bounded complete output before implementation. |
| Environment search included a missing `Backend/.env.example` path | 1 | Use the existing `DevOps/.env.example` and exact runtime configuration files; no implementation state changed. |
| Backend-submodule tracking check referenced root-owned DevOps files | 1 | Re-run the tracking check from the root repository. |
| Pytest could not write its cache directory | 1 | Treat as an environment-only warning; all 17 focused tests completed successfully. |
| Production database subprocess used an absent PowerShell variable while the ignored shared `.env` intentionally supplied a URL | 1 | Re-test with an explicit whitespace process value, which must override dotenv and be rejected after normalization. |
| Vitest does not support Jest's `--runInBand` option | 1 | Re-run the frontend suite with Vitest's native CLI and no concurrent backend workload. |
| Default parallel Vitest run produced 24 five-second timeouts plus one cascading assertion/unhandled rejection | 1 | Re-run with one native Vitest worker and a bounded 15-second test timeout to separate resource contention from defects. |
| First bounded Uvicorn restart command exited without a listener result | 1 | Inspect the exact port state and redirected startup logs before choosing a different restart action. |
| Final backend regression output exceeded the tool response context before the exit summary was visible | 1 | Re-ran the same complete suite with warnings suppressed; all 538 tests passed in 46.53 seconds. |

## Notes
- The audit and baseline were completed before the measured configuration-cache optimisation.
- The user accepted the recommended implementation roadmap on 2026-07-29.
- Never print secrets or raw employee datasets in reports.
- Re-read this plan before architectural or implementation decisions.
### Phase 9 runtime audit note

- Error: combined reads of the runtime reliability files exceeded the available output context.
- Resolution: inspect Redis, realtime, middleware, and logging modules individually with bounded reads before editing.
- Error: the first combined Phase 9 patch was rejected because one multi-file hunk was malformed.
- Resolution: no source changes were applied; split the implementation into small, independently validated patches.
- Error: seven legacy cache tests failed because `unittest.mock.patch` probes `__func__`, which the lazy proxy forwarded as a Redis operation.
- Resolution: special/dunder attribute probes now raise `AttributeError` without connecting, preserving Python introspection and existing patch points.
- Error: the focused retry still failed because Python 3.13 also probes the private `_is_coroutine_marker` attribute.
- Resolution: the Redis proxy now rejects every private attribute probe (`_...`); only public Redis commands are delegated.
- Error: a targeted frontend Socket.IO test command found no matching test files.
- Resolution: treated it as a test-discovery gap rather than a product failure; type checking passed, and realtime gating will be covered by the existing full frontend suite/build.
- Error: a second combined runtime patch was rejected because the logging hunk contained an invalid separator.
- Resolution: no changes from that patch were applied; continue with one file per patch for the remaining observability details.
- Error: a bounded frontend hook read referenced non-existent `Frontend/src/hooks/api/usePerformance.ts`.
- Resolution: use repository discovery before reading the active performance hook; the catalog and Insights hook reads succeeded and no source state changed.
- Error: the first priority-only Insights test failed schema validation because four list fields are required by `InsightsWorkspace`.
- Resolution: populate the required compact collections explicitly with empty lists, matching the existing `view=priority` response contract.
- Error: a compatibility search used an invalid regular expression while looking for exact `detail` assertions.
- Resolution: repeat compatibility inspection with simple literal searches; the failed search made no source changes.
- Error: full-directory `compileall` reported it could not list the locked `.pytest_cache` directory, although it exited successfully.
- Resolution: rely on the clean targeted compile checks for application packages/files and record the cache-directory permission warning as environment-only.
- Error: the first final task-plan status patch matched a mis-decoded em dash and found no target line.
- Resolution: re-read the file explicitly as UTF-8 and apply the completion update against the actual text.

## Phase 11: Performance+ Improvement Roadmap

- [x] Reuse the completed production audit and measured baseline instead of repeating discovery.
- [x] Define measurable frontend, API, database, report-generation, realtime, and reliability targets.
- [x] Rank improvements by evidence, impact, risk, and implementation dependency.
- [x] Produce a phased plan with acceptance gates, rollback boundaries, and release sequencing.
- [x] Review the plan against current code ownership and existing dirty worktree state.
- **Status:** completed (planning only; no product implementation authorised in this phase)

### Phase 11 errors

- Error: the first append patch targeted lines from `progress.md` as if they were at the end of `task_plan.md`.
- Resolution: inspected the exact tails of all three planning files and appended against their real final lines; no product source was affected.

### Phase 12 errors

- Error: full backend regression has one date-sensitive failure in `tests/test_report_story_service.py`; its fixture due date is 2026-07-31 while the current environment date is 2026-08-01, so the product correctly reports `Overdue` while the stale test expects `Scheduled`.
- Resolution: do not alter unrelated report-story behavior or user work; record the existing temporal fixture mismatch and run frontend verification separately.
- Error: combined final diff/status inspection exceeded the short shell timeout while traversing dirty nested repositories.
- Resolution: inspect the Frontend and Backend submodules separately with bounded commands; no source change resulted.

## Phase 12: Performance+ First Implementation Release

- [x] Add frontend bundle budgets and a `build:ci` gate.
- [x] Add component-level lazy loading for Team Dashboard charts.
- [x] Skip unused planning classification in priority-only Insights.
- [x] Add regression coverage for the priority-only compute boundary.
- [x] Run full backend/frontend regression and review the final diff.
- [x] Record release metrics and remaining roadmap phases.
- **Status:** completed with one unrelated date-sensitive backend fixture failure documented above
