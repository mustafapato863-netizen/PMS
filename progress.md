# Progress Log

## 2026-08-09 - Hostinger VPS monorepo migration

- Started a reversible implementation to consolidate the parent, Backend, Frontend, and DevOps sources into one deployable repository.
- Selected a branch-based migration with staging-first deployment; no live VPS or database mutation has been performed.
- Next: inventory current Docker/CI assets and submodule metadata, then create the migration branch.
- Created `codex/hostinger-monorepo-deploy` from the verified stable `main` commit.
- Created and verified complete Backend/Frontend Git bundles, then connected both histories to the parent merge commit.
- Converted all 278 Backend and 357 Frontend tracked files from gitlinks into normal monorepo paths at the exact pinned revisions; committed as `37ec756`.
- Confirmed the existing production Compose file has incorrect relative build paths, does not build/copy the frontend, exposes monitoring ports publicly, and maps HTTPS without certificate provisioning.
- Added the canonical Hostinger production stack: Caddy automatic TLS, Nginx static frontend, FastAPI, one-shot migrations, private Redis, and Supabase egress networking.
- Added CI and guarded Hostinger `deploy-on-vps@v2` workflows, environment templates, updated operational scripts, and a deployment/rollback runbook.
- Removed the obsolete production Compose definition under `DevOps/compose/` so `compose.production.yml` is the single production source of truth.
- Removed a hard-coded Supabase connection string from current source and changed the migration utility to require environment-provided URLs.
- Updated frontend dependencies to patched lockfile versions; `npm audit` now reports zero vulnerabilities.
- Verification passed: Backend 571 tests; Frontend 213 tests, lint, typecheck, production build and bundle budgets; Compose config; frontend/backend image builds; Nginx syntax; backend import; and container liveness/health smoke tests.
- Prepared the final branch as one sanitized commit directly on the stable parent so the old embedded credential is not carried into the unified repository history.


### Session: 2026-08-03 - Global KPI achievement cap normalization
- **Status:** in progress
- Confirmed mixed capping settings across team configuration files and the user's global 100% rule.
- Began tracing backend persistence, record resolution, frontend aggregation, and regression tests before changing configuration semantics.
- Initial focused test command used repository-root paths from inside `Backend`; it ran no tests. The next run uses paths relative to the backend working directory.
- The first bulk JSON rewrite used PowerShell's default UTF-8 BOM, which broke `json.load`; rewritten team configs with UTF-8 without BOM before continuing.
- Applied a global 100% achievement cap in the config loader, scoring service, seed/import paths, dashboard legacy-row normalization, reporting/insights evidence, and query serializers.
- Normalized all checked-in team configuration capping declarations and KPI metadata to `capped_at_100` / `cap_achievement: true`; loader normalization also protects older or uploaded configurations in memory.
- Updated frontend KPI cards, employee actions, team aggregation, team analysis, score utilities, and pre-approvals rollups so achievement never exceeds 100% and contribution never exceeds its KPI weight.
- Updated balanced-scorecard/reporting documentation and replaced legacy uncapped assertions with global-cap regression coverage.
- Focused backend verification passed: 133 tests. Full backend regression passed: 560 tests with 62 warnings.
- Focused frontend verification passed: 37 tests. Full serial frontend regression passed: 58 files / 194 tests.
- Frontend typecheck, lint, production build, and bundle-budget checks passed. `git diff --check` passed for the root and both nested repositories.
- `graphify update .` completed successfully; the graph now contains 6,196 nodes and 13,208 edges. Graphify reported only the existing zero-node JSON/SQL dependency warnings.
- One attempted full frontend command used an unsupported Vitest `--poolOptions` flag and exited before tests; the native Vitest one-worker command was then used successfully.
- After a final defensive clamp in the weighted-score helper, the complete backend suite was rerun and remained green: 560 passed in 47.16 seconds.
- A second graphify refresh completed after the final backend scoring change; the graph remains at 6,196 nodes and 13,208 edges.
- Added export/report-evidence guards so legacy report inputs cannot emit achievement or contribution percentages above their allowed cap; management Balanced Scorecard raw diagnostic ratios remain intentionally separate from operational KPI display semantics.
- Final backend regression after the export/report-evidence and legacy-insights normalization hardening remained green: 560 passed in 50.73 seconds.

### Session: 2026-08-03 - Merge OP Final teams with branch filtering
- User requested one visible team named `Pre-Approvals OP Final` combining `Pre-Approvals OP Dubai` and `Pre-Approvals OP Final SHJAJM`.
- Requested behavior: branch/region filtering, multi-select branch selection, employee/KPI scoping to selected branches, and overall score as the average across selected branch populations. Region root-cause attribution is explicitly deferred.
- Started repository and graphify audit; no product source changed yet in this session.

## Session: 2026-07-29

### Phase 7: Accepted Implementation Roadmap
- **Status:** completed through Phase 10
- Actions taken:
  - Re-opened the completed audit as a staged production-hardening and performance implementation.
  - Selected and fully read `planning-with-files`, `senior-fullstack`, and `code-reviewer`.
  - Prioritised production configuration safety, logout cache isolation, and current Pharmacy fixture compatibility before broader API optimisation.
- Errors:
  - A combined skill read was truncated; each selected skill was subsequently read separately to completion.
  - An environment search referenced a non-existent `Backend/.env.example`; useful matches were preserved and later reads will target existing files only.
  - Confirmed P0 edit targets and preserved the existing dirty worktree: backend settings/database/startup tests, frontend auth/query-client/API-client tests, and Pharmacy fixture inputs only.
  - Read the complete P0 runtime paths and confirmed a fail-fast production validator can be implemented without changing development/test SQLite support.
  - Chose a shared query cancellation/cache purge helper so explicit logout and terminal 401 handling cannot diverge.
  - Confirmed current frontend tests do not cover session termination and planned focused cache/401 coverage.
  - Confirmed Pharmacy's fifth KPI deliberately uses `score_target: 100`; only the stale actual-column fixture will change.
  - Expanded exact-name remediation to the tracked Compose manifests after confirming they pass an environment variable the backend never reads.
  - Added pure production runtime validators and enforced them for JWT, PostgreSQL, and every automatic startup seed flag.
  - Corrected the runtime CORS variable name across the tracked environment template, Compose manifests, and hosting documentation.
  - Explicitly marked the ignored local workstation override as development so fail-fast production checks do not break intentional local PostgreSQL work.
  - Added one shared client-session termination path that removes authentication, cancels active queries, and clears query and mutation caches.
  - Updated all three stale Pharmacy capping fixtures to `NoofPrescriptionAch%` without changing scoring code or team configuration.
  - Focused backend validation and Pharmacy checks passed: 17 tests.
  - Focused frontend session/cache checks passed: 4 tests across 2 files.
  - Frontend TypeScript project check passed.
  - Pytest emitted a non-functional cache-write warning because the existing `.pytest_cache` directory is access denied; test execution and results were unaffected.
  - After adding process-over-dotenv precedence, focused backend checks passed 18 tests.
  - Actual module imports rejected a missing production JWT and enabled production seed flag.
  - The first missing-database subprocess was invalid because PowerShell removed the empty variable and the ignored workstation `.env` legitimately supplied a URL; the next check will use explicit whitespace to verify process precedence and normalization.
  - Verified with an explicit blank process value that actual production database module import rejects a blank `DATABASE_URL`.
  - Completed the exact-name cleanup in the backend Vercel deployment guide and corrected settings load order so `PMS_DATA_DIR` is read after environment layers are loaded.
  - Full backend regression passed: 523 tests. The previous three Pharmacy failures are resolved by current-column fixtures.
  - Backend warnings are pre-existing deprecation/key-length/date-parsing warnings plus the local pytest-cache permission warning; no test failed.
  - The first frontend full-suite command used unsupported Jest syntax (`--runInBand`) and exited before running tests; it will be replaced with the native Vitest command.
  - The default parallel frontend run passed 160 tests but produced 24 five-second timeouts and one cascading failure/unhandled rejection under high jsdom worker load. This matches the earlier audit's contention pattern and requires a one-worker 15-second verification run before classification.
  - Full frontend regression passed with native one-worker execution: 54 files and 185 tests.
  - Frontend lint, typecheck, and production build all passed.
  - Exact-name search found no remaining operational `CORS_ORIGINS` or `JWT_SECRET_KEY` references; only the audit document's explanatory sentence remains.
  - Phase 7 production hardening is complete.
  - Began Phase 8 by mapping the active Planning, Reports, and Insights option consumers and the canonical scope helpers.
  - Confirmed the first safe projection boundary: scalar option rows can reuse existing role/team/team-level scope functions while avoiding KPI/config mapping.
  - Audited employee and management record construction and chose a backward-compatible projection/fallback design for Reports and Planning options.
  - Implemented SQL scalar option projections for employee and configured management data.
  - Migrated Planning and Reports options to those projections with compatibility fallback for injected record-service implementations.
  - Added projection/scope regression coverage; 37 focused tests pass.
  - Recovered the exact pre-projection post-cache reference metrics and authenticated probe method from the audit artifacts.
  - Detected and corrected a projection ordering compatibility issue caused by unnecessary SQL `DISTINCT`.
  - Verified zero field differences between legacy and projected outputs for both Planning and Reports options against the current local database.
  - Restarted the non-reloading local Uvicorn worker and collected final projection metrics.
  - Planning options improved from 1,985.53 ms to 120.71 ms p50; Reports options improved from 1,486.04 ms to 72.61 ms p50, with exact baseline payload byte counts restored.
  - Measured SQL statements dropping from 16 to 8 for Planning options and from 12 to 6 for Reports options.
  - Audited performance payload consumers and rejected a breaking default-summary change; selected an additive authorized catalog for the application shell.
  - Defined the minimum catalog contract needed by the shell: periods/months plus authorized team, region, level, and position scopes.
  - Added `/api/performance/catalog`, backed by SQL option rows and both canonical scope filters.
  - Migrated Sidebar and Header from the raw performance dataset to the catalog.
  - Catalog/shell focused verification passed: 4 backend tests, 9 frontend tests, and TypeScript project check.
  - Identified a second safe payload boundary: Team Dashboard can request priority-only Insights while the Insights page retains the full workspace.
  - Added backward-compatible `view=priority` to Insights and migrated only the Team Dashboard fallback consumer.
  - Priority mode preserves the summary and first ten priority insights while omitting unused detail collections and filter options.
  - Focused compact-response verification passed: 21 backend tests, 11 frontend tests, and TypeScript project check.
  - Confirmed the port-8000 process is a non-reloading Uvicorn worker started before the projection changes; it must be restarted before measuring the new implementation.
  - The first bounded restart did not return a listener confirmation; startup logs and exact port ownership will be inspected before any retry.

### Phase 1: Current-State Audit and Baseline
- **Status:** completed
- **Started:** 2026-07-29
- Actions taken:
  - Read and decomposed the full production-stack audit request.
  - Selected and loaded `planning-with-files`, `senior-fullstack`, and `code-reviewer`.
  - Created persistent audit plan, findings, and progress records.
  - Inventoried the repository root, nested Git submodules, runtime entrypoints, and deployment/configuration files.
  - Confirmed that no production code was changed for the audit.
  - Traced frontend token storage, query-client defaults, application initialisation, and logout behaviour.
  - Traced backend engine/session creation, authentication middleware, error handling, Redis fallback/invalidation, Socket.IO process state, and Vercel manifests.
  - Recorded initial security, cold-start, cache-scope, error-contract, and environment-variable findings.
  - Captured the 118-operation live OpenAPI inventory and enumerated active frontend request call sites.
  - Inspected the live local PostgreSQL schema, row counts, primary/foreign/unique constraints, and indexes for 55 inspector-visible tables.
  - Produced all ten requested audit, baseline, architecture, decision, rollback, results, and final-report documents.
  - Implemented mtime-aware parsed configuration caching and per-request resolved-config reuse.
  - Verified identical response hashes and measured 55.9%–76.4% p50 improvement across the four targeted read flows.
  - Passed 4 focused change tests, 129 focused backend regressions, frontend build/typecheck/lint, and isolated slow frontend tests.
- Files created/modified:
  - `task_plan.md` (created)
  - `findings.md` (created)
  - `progress.md` (created)

### Phase 2: Baseline
- **Status:** completed
- Actions taken:
  - Captured authenticated endpoint, payload, query-count, SQL-time, EXPLAIN, relation-size and frontend-build evidence.
  - Repeated the targeted endpoint measurements after the implementation.
- Files created/modified:
  - `PERFORMANCE_BASELINE.md`
  - `PERFORMANCE_RESULTS.md`

## Test Results
| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
| Config cache tests | 4 focused tests | Pass | 4 passed | Passed |
| Backend focused regression | 129 tests | Pass | 129 passed | Passed |
| Backend full suite | Current tree | Pass | 538 passed | Passed |
| Frontend build | Production bundle | Pass | Passed | Passed |
| Frontend typecheck/lint | Current tree | Pass | Passed | Passed |
| Frontend full unit suite | Current tree | Pass | 55 files, 187 tests passed | Passed |
| Chromium E2E/accessibility | Release smoke | Pass | 6 tests passed | Passed |
| Response compatibility | Four optimized endpoints | Identical bytes/body | Identical status, bytes and SHA-256 | Passed |

## Error Log
| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|
| 2026-07-29 | Large parallel backend file reads were truncated by the output-context limit | 1 | Use targeted `rg -n` searches and bounded line ranges. |
| 2026-07-29 | Eleven-endpoint TestClient/query-instrumentation baseline exceeded 120 seconds | 1 | Split latency and query-count measurements into smaller bounded probes. |
| 2026-07-29 | Relation-size SQL failed because `oid` was ambiguous after joining `pg_class` and `pg_namespace` | 1 | Re-run with `c.oid`; no state changed. |
| 2026-07-29 | Focused pytest included a test file that does not exist | 1 | Re-run the actual new test module. |
| 2026-07-29 | Backend virtualenv has no Ruff module | 1 | Use compile/test verification and record lint as unavailable. |
| 2026-07-29 | CIM command-line lookup for the port-8000 process timed out | 1 | Use lighter bounded process inspection. |
| 2026-07-29 | `wmic` is not installed | 1 | Used `netstat` plus exact-PID `Get-Process` instead. |
| 2026-07-29 | Final backend regression output was truncated before the summary was visible | 1 | Re-ran the complete suite with `--disable-warnings`; all 538 tests passed in 46.53 seconds. |
| 2026-07-29 | Regression command used assumed API test filenames that are not present | 1 | Discover and run the actual Insights, Planning, Reports, Auth and router tests. |
| 2026-07-29 | 8 frontend tests timed out at 5 seconds under concurrent CPU-heavy backend verification | 1 | Re-run serially with a 15-second per-test bound. |
| 2026-07-29 | Serial full frontend suite exceeded five minutes | 1 | Isolate the six previously failing files instead of repeating the full suite. |
| 2026-07-29 | Full backend suite: 3 Pharmacy capping tests fail because fixtures omit the current `NoofPrescriptionAch%` column | 1 | Do not change scoring/config semantics in a performance audit; record as pre-existing contract debt. |
| 2026-07-29 | Full frontend suite: password-modal test exceeded the default five-second timeout | 2 | It passes in the isolated slow-test run; classify as timing flakiness. |

## 5-Question Reboot Check
| Question | Answer |
|----------|--------|
| Where am I? | Completed the audit, implementation, and local release gate |
| Where am I going? | Staging role/scope smoke and production rollout are the next release activities |
| What's the goal? | Measured, safe full-stack performance improvement without business or security regressions |
| What have I learned? | See `findings.md` |
| What have I done? | Implemented Phases 7-10, produced final evidence, and verified compatibility/release checks |
## Phase 9 runtime reliability

- A combined read of the runtime reliability modules exceeded the output context.
- Switched to bounded, one-file-at-a-time inspection for Redis, realtime, middleware, and logging.
- A combined Phase 9 patch was rejected before applying any source changes due to a malformed multi-file hunk.
- Split the implementation into smaller patches so each change can be syntax-checked independently.
- The first focused runtime test run produced 7 failures: `unittest.mock` introspection reached the lazy Redis proxy through `__func__`.
- Fixed the proxy to reject dunder introspection locally; no Redis connection is attempted for Python metadata checks.
- Python 3.13 performed a second private introspection probe (`_is_coroutine_marker`), so the first compatibility correction was incomplete.
- Expanded the guard to all private names while retaining delegation for public Redis commands.
- Focused Phase 9 backend verification passed: 32 tests covering lazy Redis behavior, cache fallbacks, monitoring headers/errors, and production runtime validation.
- Backend compile checks and `git diff --check` passed for the runtime changes.
- Frontend type checking passed after adding explicit realtime gating.
- A targeted socket-hook test command returned “No test files found”; no existing socket-hook test files are present, so verification continues through the full suite and production build.
- A combined Redis/logging/CORS patch was rejected before applying because of an invalid logging hunk; the remaining edits were split per file.
- Redis command failures now enter the same retry cooldown as initial connection failures.
- Focused Redis/cache/monitoring verification passed again (20 tests), frontend lint passed, and whitespace checks passed.
- Added backend/frontend realtime flags and documented Redis timeout/retry controls across environment templates and Compose profiles.
- Restarted the exact verified local Uvicorn listener onto the current source; startup completed without import-time Redis work.
- A smoke request exposed protected liveness/readiness probes; corrected the auth exemption and added two regression cases. Focused auth/monitoring/provider verification passed (44 tests).
- One attempted frontend hook read used a non-existent filename; switched back to file discovery for the active hook.
- Restarted again after the probe fix and confirmed anonymous `/api/health/liveness` returns 200 with request/timing headers.
- Completed five-sample live measurements for Performance, catalog, full Insights, and priority Insights; recorded latency, bytes, item counts, and diagnostic-header presence without printing credentials or employee data.
- Captured warm SQL counts: Performance 9, catalog 5, full Insights 14, priority Insights 14.
- Added a priority-only Insights generation path to skip unused option, people/trend, team-summary, risk-card, and driver response work while preserving the same ranked priority items and summary.
- The first focused test exposed four required schema collections in the early return; corrected them to explicit empty lists.
- Priority-only Insights focused verification passed (43 tests), and its live response is byte/field-equivalent to projecting the default full workspace.
- One compatibility grep expression was malformed; switched to literal searches before implementing the canonical additive error envelope.
- Added the canonical additive error envelope and retained existing `detail` values/lists for frontend and external compatibility.
- Focused auth, runtime, and monitoring verification passed (54 tests); compile and whitespace checks passed.
- Completed configuration-name and migration-head checks. Local PostgreSQL is at the single current Alembic head `e4a7c1d9b520`; no new migration was introduced.
- Full backend regression passed: 536/536 tests. Remaining output is limited to known dependency/deprecation and unwritable pytest-cache warnings.
- Full serial frontend regression passed: 55 files and 187/187 tests.
- Frontend type check and lint passed. A root-level compile sweep could not enumerate the locked `.pytest_cache`; targeted application compile checks had already passed.
- Frontend production build passed (3,298 modules transformed in 1.80 seconds).
- Targeted Chromium release smoke passed: 6/6 layout, responsive-navigation, route-overflow, dialog-accessibility, and serious accessibility checks.
- Final code review caught duplicate 5xx metric increments and incomplete health-probe exclusion; both were fixed and covered by focused tests.
- Removed import-time `DATA_DIR` creation. Focused monitoring/runtime verification passed (22 tests), plus compile and whitespace checks.
- Re-ran the complete backend suite after the review fixes: 538/538 passed.
- Replaced the interim performance and implementation reports with the final Phase 7-10 metrics, verification evidence, release status, and rollback boundaries.
- Updated production requirements, cache architecture, migration/rollback guidance, and marked Phases 8-10 complete in the task plan.
- Restarted the exact local Uvicorn listener onto the final source after the log-privacy hardening. Final smoke confirmed public health 200, canonical 422 validation, canonical 401 auth rejection, matching request IDs, timing headers, and `route=unmatched` rather than a raw protected path. The current listener is PID 6252.
- Re-ran the complete backend suite with bounded output after the final privacy change: 538/538 passed in 46.53 seconds.
- Final log-safety review removed raw-path fallback from request and error telemetry so pre-routing failures cannot record path identifiers.

## Session: 2026-08-01 — Performance+ Roadmap

- Selected `planning-with-files`, `senior-architect`, and `code-reviewer`.
- Confirmed `graphify-out/graph.json` is absent, so planning uses repository evidence and existing audit artifacts.
- Verified the current frontend production build succeeds and captured current chunk sizes.
- Began Phase 11 as planning-only work; no application, schema, environment, or deployment changes have been made.
- Read the current baseline/results/database/final implementation artifacts and separated already-delivered improvements from remaining opportunities.
- Created `PERFORMANCE_PLUS_ROADMAP.md` with quantified targets, seven delivery phases, acceptance gates, technology decisions, ownership, risks, rollback boundaries, sequencing, estimates, and approval checkpoints.
- Completed Phase 11 planning. Product implementation remains intentionally unstarted.

## Session: 2026-08-01 — Performance+ Implementation Kickoff

- Re-read the Performance+ roadmap and selected the first implementation release scope.
- Confirmed existing Backend/Frontend dirty work must be preserved.
- Initial source discovery shows the shared App shell imports Framer Motion and existing Performance/Insights hooks are the correct extension points.
- No product source has been edited in this implementation session yet.
- A bounded source read used an assumed SQL repository path that does not exist; no source change occurred. The next inspection will resolve the import path before editing.
- Added Frontend `budget` and `build:ci` scripts with raw/gzip limits for charts, animation, and Team Dashboard chunks.
- Initially removed route-level `AnimatePresence`, then measured no chunk-size benefit because shared shell components still import Framer Motion; reverted that behavior-only change.
- Added a regression test proving priority-only Insights skips unused planning classification.
- Inspected the management and SQL repository paths; period-scoped priority loading is a separate higher-risk optimization and was not mixed into this first safe patch.
- Verification passed: backend Insights tests 19/19, frontend typecheck, lint, targeted Reports/Insights tests 6/6, production build, bundle budgets, and whitespace checks.
- Identified `TeamChartsSection` as a below-the-fold synchronous import in the Team Dashboard; preparing a component-level lazy boundary as the next safe frontend optimization.
- Implemented the Team Dashboard chart lazy boundary with an accessible loading skeleton; typecheck, build:ci, bundle budgets, focused backend tests, and diff checks passed.
- Full backend suite result: 540 passed, 1 pre-existing date-sensitive failure in `test_report_story_service.py`; no performance-path test failed. Frontend full-suite result is being run separately after the combined command stopped on the backend failure.
- Full frontend suite passed: 55 files / 189 tests.
- Phase 12 implementation scope is complete; remaining Performance+ phases (period-scoped Insights loader, compact Performance consumer migration, async report jobs, hosting/realtime migration, staging load) remain intentionally separate.
- Final combined diff inspection timed out; bounded submodule checks remain before closing the implementation session.
- Added `PERFORMANCE_PLUS_IMPLEMENTATION.md` with the actual changes, measurements, verification, and remaining roadmap work.

## Session: 2026-08-03 — Pre-Approvals IP Elective Dubai onboarding

- Read the supplied onboarding notes, current IP Final/OP cleaners, config validation rules, seeding flow, and score calculation semantics.
- Confirmed the existing IP Final Dubai configuration must remain untouched; the new team gets its own config and cleaner.
- Added the dedicated team JSON, deterministic cleaner, Excel/seeding registrations, API/action/team navigation mappings, and a timer icon for the new sidebar entry.
- Added six backend tests covering configuration, formula scoring, exclusions, ambiguous workstreams, dry-run import, and config API discovery; all passed.
- Verification passed: full backend suite 547/547, frontend typecheck, targeted navigation tests 2/2, production build, compile checks, diff whitespace checks, and graphify update.
- The exact `.xlsx` workbook is still needed to confirm its final header order/spelling and real missing-value patterns before production upload.

## Session: 2026-08-03 — PMS_Trend_All.xlsx validation

- Workbook path received: `D:\Trend\PMS_Trend_All.xlsx`.
- Started a metadata-only workbook audit before changing onboarding code; no production or database writes are authorized by this request.
- Found the target sheet's real header row and combined turnaround columns; the existing cleaner will not parse this sheet as-is and needs a compatibility path based on the target columns.
- A full workbook load timed out; switched to read-only iteration for the remaining formula and value checks.
- The first score-comparison probe was a script syntax error only; no application code was affected.
- The first compatibility test run exposed the expected header-source mismatch; the cleaner now supports both the production title-row workbook and normalized header-row uploads.
- Updated the cleaner to detect the actual second-row header, support the combined turnaround column, classify from the complete target pair (including historical target revisions), preserve row-level targets, and expose canonical source counters for frontend aggregation.
- Dry-run of the complete `PMS_Trend_All.xlsx` passed with no failed teams; the new team contributed 40 cleaned/scored rows and the full workbook produced 1,028 records.
- Direct recalculation of all 40 active new-team rows reproduced the workbook's stored scores to floating-point precision.
- Full Backend regression passed: 549/549 tests. Graphify incremental update completed with the new cleaner and validation paths included.

## Session: 2026-08-03 — Confirm target-pair workstream pattern

- Received an updated `D:\Trend\PMS_Trend_All.xlsx` and started a second metadata/formula audit; no database writes yet.
- Inspected the refreshed target columns and confirmed the four historical target pairs; added pair-aware workstream classification with explicit rejection of missing/unsupported combinations.
- Added configuration and regression coverage for the observed target revisions (`3%/75%`, `6%/75%`, `1%/100%`, `3%/100%`).
- Recalculated the source formulas from raw counts and matched all 40 active rows exactly; full workbook dry-run completed with 1,028 records and no failed teams.
- Full Backend suite passed 550 tests and graphify was refreshed after the implementation.

## Session: 2026-08-03 - Pre-Approvals OP Final SHJ/AJM onboarding

- Started a new onboarding scope for the `Pre-Approvals OP Final SHJAJM` worksheet.
- Read the supplied 60/40 KPI formulas and exception behavior.
- Audited the target worksheet: row-1 headers, 23 active measurable rows (AJM/SHJ), one Leave row, and formula columns matching the supplied 60/40 table.
- Confirmed explicit registrations are required in cleaner factory, Excel processor, and seeding service; KPI service needs a safe conditional exception for unavailable TAT.
- Workbook and existing OP Final paths were inspected before implementation.
- Implemented the SHJ/AJM cleaner, isolated team configuration, import/seeding registrations, frontend route/sidebar mappings, and the config-driven missing-TAT scoring exception.
- Workbook dry-run succeeded with no failed teams; the new sheet contributed 23 active rows. Full backend regression passed 554 tests; frontend regression passed 193 tests, typecheck/lint/build/bundle budgets passed, and graphify was refreshed.

## Session: 2026-08-03 - Pre-Approvals IP SHJ/AJM onboarding

- Started onboarding for `Pre-Approvals IP Final SHJAJM` using the supplied 40/60 baseline-80 formulas.
- Confirmed the target sheet is row-1 based, with KPI reference text to the right of the data table; implementation must crop/process only the employee columns and preserve SHJ/AJM branch values.
- Next: audit all data rows and cached formula values, then add isolated cleaner/config/registrations and tests.
- First audit probe printed the complete four-row dataset and formula samples, then hit an out-of-range debug index while requesting a non-existent sixth data row; no source changes resulted.
- The bounded reconciliation probe confirmed four active rows (2 SHJ, 2 AJM), targets of 100%/100%, and exact score parity with the workbook.
- Implemented the IP SHJ/AJM cleaner, config, cleaner-factory/Excel/seeding registrations, frontend route/sidebar mapping, and focused regression tests.
- Complete workbook dry-run succeeded with no failed teams: 1,055 records and 255 employees, including both SHJAJM teams.
- Release verification passed: Backend 558 tests, Frontend 194 tests, frontend typecheck/lint/build/bundle budgets, and graphify update.

## 2026-08-03 — OP Final KPI achievement cap correction

- Changed `Pre-Approvals OP Final SHJAJM` so both KPI achievements are capped at 100% and the final score is capped at 100%.
- Updated the scoring service to persist capped achievement ratios for explicitly capped KPIs.
- Added dashboard API normalization/recalculation so legacy rows with uncapped or decimal scores return consistent KPI evidence, score, and grade.
- Updated frontend team analysis and employee action details to honor the API cap metadata.
- Verification: Backend `559 passed`; Frontend `194 passed`; typecheck, lint, production build/bundle budget, and graphify update all passed.

## 2026-08-03 - OP Final branch merge and multi-select filter

- Added the canonical presentation team `Pre-Approvals OP Final` while retaining both source team names and their independent scoring configurations.
- Replaced the two duplicate sidebar entries with one canonical route; legacy slugs remain compatible aliases.
- Added a multi-select branch control for Dubai, Sharjah, Ajman, and Clinics. Selection is persisted in the URL and scopes employees, headcount, trends, KPI aggregation, and the merged team's employee-score average.
- Added backend repository and authorization aliases so direct dashboard queries and exports can resolve the canonical team without a schema/data migration.
- The requested per-KPI region attribution/root-cause analysis remains intentionally deferred.
- Verification: Backend full suite `560 passed`; Frontend full suite `194 passed`; frontend typecheck/lint/production build/bundle budget passed; graphify refreshed successfully.

## 2026-08-03 - Branch precedence correction

- Confirmed the source `Team` values are present (`AJM`/`SHJ`) and the defect was in frontend filtering order: synthesized geo activity was evaluated before the explicit branch field.
- Changed branch matching to treat source `Team`, `Branch`, `Site`, and `Area` as authoritative; geo totals are now fallback-only for legacy call-center rows.
- Made merged OP Final KPI weights prefer the active configuration when persisted KPI rows contain stale weights, preventing the 40% TAT KPI from displaying as 100%.
- Added a regression test proving an AJM row with activity in every geo bucket still matches only Ajman.
- Final verification after the correction: Frontend `195 passed`; typecheck/lint/build/bundle budget passed; graphify refreshed.

## 2026-08-03 - Merge IP Final Dubai and SHJ/AJM

- Added one canonical `Pre-Approvals IP Final` sidebar route while keeping legacy source slugs compatible.
- Added frontend canonicalization, source-team access handling, and the same multi-branch selector used by OP Final.
- Merged source configs by position, preserving Dubai workstream weights and SHJ/AJM 40/60 baseline scoring.
- Added backend performance, authorization-scope, and action-service aliases for canonical IP Final requests.
- Verification passed: Frontend `196` tests plus typecheck/lint/build/bundle budgets; Backend `562` tests; graphify update completed.

## 2026-08-04 - UAE Pre-Approvals parent consolidation

- Added parent/workflow aliases and route metadata in `Frontend/src/types.ts`.
- Added URL-backed workflow filter and parent workflow summary component.
- Updated team dashboard filtering, access checks, export workflow routing, and UAE sidebar navigation.
- Updated backend repository/report-scope aliases and export workflow handling.
- Added frontend and backend regression tests for parent matching, workflow separation, and team-level scope expansion.
- Verification: Frontend lint, typecheck, `202` tests, production build/bundle budget; Backend full suite `566 passed`.
- Graphify update completed after the final source changes; no commit or deployment performed.
- Enhanced the parent workflow summary cards with restrained neon hover/focus states and click-through to the corresponding workflow filter; interaction regression coverage now brings the frontend suite to `203` tests.

## 2026-08-04 - Call Center parent/channel consolidation

- Added the canonical `Call Center` parent route and replaced the duplicate Egypt `Inbound`/`Outbound` sidebar entries with one parent entry; legacy source routes remain compatible.
- Added a URL-backed `All Channels` / `Inbound` / `Outbound` filter and clickable neon channel summary cards. The parent view intentionally avoids pooled KPI cards; selecting a channel loads that channel's own KPI configuration and score calculations.
- Kept `Inbound UAE` outside the parent scope and preserved direct channel authorization boundaries. Parent access expands to both Egypt channels, while access to one source channel does not grant the other.
- Updated backend repository aliases, report-scope authorization, and Excel export channel handling without a schema migration or source-data rewrite.
- Added frontend/backend regression coverage for parent mapping, channel classification, scope isolation, and card navigation.
- Verification: Frontend `207` tests, typecheck, lint, production build/bundle budget, and code-quality checker passed; Backend `568 passed`; graphify refreshed successfully.
