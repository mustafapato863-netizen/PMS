# Applied basis consistency — bounded QA lane

## Independent reviewer acceptance evidence (latest; supersedes historical limits below)

This is a bounded local QA checkpoint, not production release approval. Codex independently inspected the source/test diff and ran these checks after Grok run8 ended:

- Full frontend: 736 tests in 99 files passed (177.89s), then passed again after the final test-only consolidation (167.27s). Final lint and type checking passed; production build and unchanged bundle budgets passed on unchanged production code. No assertion was removed or relaxed.
- Full backend: 1152 passed, one known external Marketing workbook failure (available 131 rows versus asserted 68), one existing skip, 243.66s. The suite is NOT fully green. No skip, fixture alteration or tolerance relaxation hides this exception.
- Actual JWT/browser lifecycle passed with both frontend scoped-data modes. Anonymous access returned 401; Performance Team and Function Director ordinary reads returned 200 and evaluation management returned 403. Synthetic owned SQLite fixtures only; no dependency-injected identity.
- July score 82.85 remains unchanged. August baseline 79.82, revised applied score 79.93, rollback 79.82 are verified across legacy/bounded performance, summary/trends, employee history, Insights, report-center and regenerated report preview APIs. Approval alone does not recalculate. Original workbook values remain unchanged.
- Actual Function KPI table and EmployeeProfileView display Attendance target 65 -> 70 -> 65, weight 60 -> 50 -> 60, and Productivity weight 10 -> 20 -> 10. Same-client SPA Team revisit and fresh JWT Team also reflect the applied basis. This does not prove warm SPA behavior on every other page.
- Actual API-backed Function DriversCard displays Attendance 46.1% / -9.2% and Booking 30.1% / +13% rather than fractional 0.5% / 0.3%. Impact and rank are unchanged. The Departmental composition is separately tested by the real React card regression, not claimed as a production browser acceptance.
- Independent mapper/configuration/aggregate/card probe preserves 0.7142857142857143 score points and displays Contribution0.7% / Weight50%. The original pooled pinned contribution remains 35.714285714285715. No aggregation policy was standardized between individual, team and function views.
- Restored Team and Function layouts have no document overflow at 390, 746, 1024 and 1440 pixels. These two pages in one theme are not a complete responsive/theme audit.
- AST graph update passed (9569 nodes, 26033 edges, 410 communities). JSON empty-node and missing SQL parser warnings remain; no LLM labeling was run.

NOT RUN: disposable PostgreSQL/migration verification, every team/formula/role/page, multi-worker or Redis load, production-built browser performance benchmarks, and the measured optimization lane. Do not infer those from the tests above. No production DB writes, private-workbook edits, push, main merge or deployment.

Resource observation only: 1000 anonymous rows with ten result revisions retain 10000 serializer entries (~27.7 MB traced Python allocations) with zero stale reads. The newest latency run overlapped tests/graph work and is not a valid speed baseline. Repeat uncontended from this checkpoint before any before/after optimization claim. Keep full evidence fingerprints; ID-only caching is stale and is not an acceptable memory optimization.

Date: 2026-10-09. Worktree: `codex/evaluation-qa-consistency`. Baseline: `b2187144f3940e8680866e10b9fff25e480fce97`. No commit, push, merge, deploy, production database write, credential change, or private-workbook edit.

This lane checks three remaining defects after the pooled team score was already accepted at `35.714285714285715`. It does not accept the product for release. It does not exercise real JWT login, PostgreSQL, browser widths and themes, or a performance pass.

## What this lane actually tests

| Check | Result | Boundary |
| --- | --- | --- |
| Employee report evidence keeps a trusted applied pin, including a KPI the static file does not define | Pass | Real Outbound file. Dict row, `DashboardRecordService` schema record, and a non-dict KPI object |
| Unpinned KPI missing from the static file stays excluded and visible as a configuration failure | Pass | Same Outbound file. Attendance weight `0.5` still mismatches file weight `0.70` when the row is not pinned |
| Direct team aggregate treats opposite direction, unit, or KPI identity as a varied basis in either input order | Pass | `aggregateConfiguredTeamKpis`, including the live Outbound file through `mapScopedPerformanceRecord` |
| Scored cohorts with different directions keep their own scores and a headcount combination | Pass | Score is not forced to 0. Disagreeing targets are not averaged |
| Legacy position variation keeps the previous headcount rollup and is not labeled as an applied pin | Pass | Synthetic Agent and Lead positions |
| Fixed call-center cards and an extra KPI follow applied direction and varied metadata | Pass | React `TeamKpiSection` renders. No browser viewport or theme pass |
| Uniform pinned pool remains `(0.5 / 0.7) * 0.5 * 100` | Pass | Independent SSR probe and the worktree regression |
| Real JWT login, PostgreSQL, downstream pages beyond these modules, browser widths and themes | Not run | Prior full-suite counts do not cover those surfaces |

## Reporting

The static Outbound file defines Attendance at weight `0.70` and does not define Productivity. An Employee row whose KPI carries `evaluation_pinned: true` now uses that stored KPI as the applied basis.

Reproduced before the fix: Productivity was dropped as `persisted_kpi_missing_configuration`, and Attendance weight `0.5` was reported as `weight_mismatch` against the file weight `0.70`.

After the fix, for actual `0.46`, target `0.7`, weight `0.5`, and stored contribution `(0.46 / 0.7) * 0.5`:

- Attendance stays in the evidence with direction `lower_better`. The existing direction resolver already kept that direction, so this lane does not add a second direction override.
- The normalized weight is `50` and the normalized contribution is `32.85714285714286`. That is the stored contribution on the reporting percent scale. It is not recalculated from the file weight `0.70`.
- Productivity is present with weight `20` and contribution `19.5`, which is `(0.78 / 0.8) * 0.2 * 100`.
- The independent probe's issue list is empty. File-only template KPIs are not reported as missing evidence when every persisted KPI is a trusted pin.
- An unpinned unknown KPI is still excluded with `persisted_kpi_missing_configuration`. An unpinned Attendance weight of `0.5` still raises `weight_mismatch` with expected `70` and actual `50`.

The same assertions pass through `_pinned_schema_record` into `SchemaPerformanceRecord` and then `ReportingEvidenceService._normalized_record_kpis`. The pin flag is also read from a non-dict KPI object.

Paths: `Backend/services/reporting_evidence_service.py`, `Backend/services/dashboard_record_service.py` (mapper used, not edited), `Backend/tests/test_reporting_applied_employee_basis.py`.

## Direct aggregate

`aggregateConfiguredTeamKpis` previously compared only pinned target and weight. The first row's direction was kept, so the same target `0.7` and weight `0.5` with opposite directions reported `basisVaries: false`, and reversing the rows flipped `isLowerBetter`.

A pinned bucket now also compares direction, unit, and KPI key. A disagreement sets `basisVaries: true`, target `NaN`, weight `null`, contribution `null`, and leaves `isLowerBetter` unset. Both input orders agree. When the units agree, the returned `unit` stays. When the pin keys agree, the returned `key` stays. A disagreement clears only the field that disagrees. A single uniform pin is unchanged: key `Attendance`, unit `%`, target `0.7`, scored weight `0.5`, pooled contribution `35.714285714285715`. The raw workbook target `0.65` stays on the source row.

That comparison is inside one `aggregateConfiguredTeamKpis` bucket. Rows that `basisGroupKey` has already split are merged later by `calculateAggregatedTeamPerformance`. The cohort-merge section below covers that second step. The gate counts in the first table are from the earlier lane. They do not include the cache-identity or cohort-merge edits.

Scored groups were already separated by applied signature. Their team score remains the headcount-weighted combination of those cohort scores. Compatible productivity still contributes `(0.7780694444444445 / 0.8) * 0.2 * 100`. Incompatible targets are not averaged to `0.675`, and the team score is not replaced with `0`.

Pure legacy position variation does not enter that varied-pin path. For one Agent at actual `80`, target `100`, weight `0.4`, higher-better, and one Lead at actual `80`, target `50`, weight `0.6`, lower-better:

- Agent contribution = `(80 / 100) * 100 * 0.4` = `32`
- Lead contribution = `(50 / 80) * 100 * 0.6` = `37.5`
- Displayed target = `75`, weight = `0.5`, contribution = `34.75`
- `evaluationPinned` is not true, and `basisVaries` is not true

An applied pin that disagrees across those positions still blanks target, weight, and contribution, and still does not average the targets.

Paths: `Frontend/src/features/team/teamKpiAggregator.ts`, `Frontend/src/features/team/teamKpiAggregator.pinnedBasis.test.ts`.

## Call-center cards

`TeamKpiSection` previously applied the varied state only to additional cards. Fixed cards turned a non-finite applied target into the static fallback (Outbound attendance `55`, booking `46`, reachability `75`, handle time `2:30`, inbound attendance `75`, utilization `85`, abandon `1`) and turned a null varied weight back into the file weight. A null varied weight also hid Quality and an extra KPI such as Productivity. Opposite-direction pins still used the hardcoded higher-better or lower-better badge.

When a fixed or additional KPI has `basisVaries` or a non-finite target, the card now shows `Varies`, `Basis varies`, `Applied basis varies`, no progress, and blank weight and contribution. Quality and Productivity stay visible. A uniform applied direction drives the badge and progress: attendance actual `60` against target `70` with lower-better is `On Target` at `116.7%` of target; handle time `100` seconds against `150` seconds with higher-better is `Below Target` at `66.7%` of target.

Legacy cards with no applied pin still use the static targets, including Outbound attendance `55` and inbound attendance `75`. The grid stays four columns without Quality and five columns when Quality is shown. A zero-weight handle-time row stays visible as a diagnostic with weight `0%` and target `2:30`.

Path: `Frontend/src/components/team/TeamKpiSection.tsx` and `TeamKpiSection.test.tsx`.

## Gates on this worktree

Environment for backend commands: `APP_ENV=test`, `DATABASE_URL=sqlite:///:memory:`, empty `REDIS_URL`, `CI` unset. PostgreSQL was not run.

| Gate | Result |
| --- | --- |
| `pytest` reporting applied-basis, basis-annotation, evidence, and report-story tests | 46 passed |
| Independent reporting probe `reviewer-reporting-applied-probe.py` | Pass. Productivity present, Attendance direction `lower_better`, issues empty, stored contribution `32.85714285714286` |
| Aggregator and `TeamKpiSection` vitest, re-run after the final direction-flag edit | 26 passed, 2 files |
| Independent aggregation probe with `--mixed-direction` | Pass. Pooled contribution `35.714285714285715`. Direct `basisVaries` true for either order |
| Frontend ESLint | Pass |
| Frontend `tsc -b` | Pass, including a null-weight type fix found by the first typecheck |
| Frontend `vitest run` before the final unset-direction edit | 719 passed, 94 files, 81.13s |
| Frontend `vitest run` after that edit | 719 passed, 94 files, 87.58s, exit 0 |
| Frontend `build:ci` and existing bundle budgets | Pass. Budgets were not raised. This gate ran before the final one-line unset-direction edit |
| Backend `pytest` from `Backend/` | 1149 passed, 1 failed, 1 skipped, 233.78s. The failure is the known Marketing workbook assertion `131 == 68` in `test_real_marketing_workbook_imports_with_incomplete_rows_excluded`. It was not skipped, weakened, or edited |

ESLint and `tsc -b` also ran before the final unset-direction edit. That edit only leaves `isLowerBetter` unset when the applied basis already varies, and the field is already optional. The 26-test aggregator and card re-run and the second full frontend run both include that edit. No existing test was skipped, no tolerance was widened, and no bundle budget was raised.

## Not claimed

This lane does not show that every report, dashboard, or analysis page agrees after a real authenticated apply. It does not show PostgreSQL row-level security, a second browser session, role revocation, or Redis-down behavior. Saved report snapshots, human-authored actions, notes, plans, owners, and commitments were not rewritten. The performance lane was not started.

## Cohort merge and serialization identity

Run 4 exited at max turns with these source defects still open. The cache implementation already in the tree was kept. This follow-up closes the remaining cohort-merge counterexample and the non-scoring serialization identity gap, then re-runs the gates.

### Cross-cohort pin identity

`basisGroupKey` already separates pools when the raw pin unit or pin key differs. Each pool is internally uniform, so `aggregateConfiguredTeamKpis` can report `basisVaries: false` for that pool alone. The merge in `calculateAggregatedTeamPerformance` was then treating two pools with the same label as compatible when direction, formula, target, and weight matched. It kept the first pool's unit and key and headcount-averaged the actuals. The label lookup key remains `attendancerate`.

`getKPIsForAgent` maps a unit outside `%`, `min`, `number`, and `currency` to `number`. A raw pin unit of `count` therefore reaches the merge as `number` when the row is mapped again. The worktree regression sets `count` on an already mapped row, so the compared units are `%` and `count`. Either pair is incompatible.

For an applied pin, a unit difference or a pin-key difference now sets `basisVaries: true` in both input orders. The conflicting field is cleared and the shared field is kept:

| Case | Map lookup | `key` | `unit` | `actual` | `weight` / `contribution` |
| --- | --- | --- | --- | --- | --- |
| Same label, units `%` and `count` | `attendancerate` | `Attendance` | unset | `NaN` | `null` |
| Same label and unit, keys `Attendance` and `Distinct Attendance` | `attendancerate` | unset | `%` | `NaN` | `null` |
| One uniform Attendance pin | `attendancerate` | `Attendance` | `%` | scored value | scored weight `0.5`, contribution `(0.5 / 0.7) * 0.5 * 100` |

Target is `NaN` and `isLowerBetter` is unset on the incompatible rows. The actual is not the mean of the two cohort actuals. The regression uses actuals `0.46` against `0.9` (unit) and `0.46` against `0.2` (key), so a silent average would be visible. A direction, formula, target, or weight disagreement that still shares unit and key keeps that shared identity and still headcount-averages the actual.

Legacy Agent/Lead position variation stays on the previous headcount rollup: displayed target `75`, weight `0.5`, contribution `34.75`, and `basisVaries` is not true. Non-finite merged values render as `—` in `formatKpiValue` and `formatTeamKpiValue`. The fixed attendance card still reads `teamMetrics.attendCR`.

This is the reviewer-confirmed merge bug on the SSR probe inputs. It does not show that every production scope contains mixed-unit pins.

Test: `does not merge pinned cohorts that share a label but not a unit or KPI identity` in `Frontend/src/features/team/teamKpiAggregator.pinnedBasis.test.ts`. Paths: `Frontend/src/features/team/teamKpiAggregator.ts`, `teamKpiAnalysis.ts`, `Frontend/src/components/team/TeamKpiSection.tsx`, `Frontend/src/components/common/performanceKpiProgress.ts`, `Frontend/src/pages/TeamDashboardView.tsx`.

The reviewer probe `reviewer-evaluation-aggregation-probe.mjs` (`--mixed-unit-key` and `--mixed-key`) was not executed again from this lane.

### Serialization cache identity

`serialization_cache_key` remains `ser:{record id}:{year}:{sha256}`. The digest is `json.dumps(..., sort_keys=True)` of the stored inputs `serialize_performance_record` reads:

`id`, `employee_id`, `employee_name`, `year`, `month`, `team`, `region`, `branch_key`, `performance_level`, `position`, `status`, `upload_id`, `meta`, `evaluation`, `raw_data`, `kpi_values` in stored order (full dicts, including passthrough keys), `calls`, `actual`, `achievement`, and `geo`.

The key text contains the record id, the year, and the digest. Names and other field values stay inside the hash. Dict key order is a cache hit. KPI list order follows the stored list. The same id in another year is a different key. An old `ser:{id}` entry can remain until its TTL and is not the key this function reads.

`test_warmed_serialization_follows_identity_metadata_and_kpi_passthrough` warms one row, then revises `employee_name`, `employee_id`, `region`, `branch_key`, `performance_level`, `position`, `upload_id`, and `meta` one field at a time. Each revision returns the new value, misses the warmed object, and changes the digest. A KPI `source_note` also misses. Meta `{"b": 2, "a": 1}` and `{"a": 1, "b": 2}` share one cached object. The same test keeps the human note and raw `T.Attend%` `0.65`.

Reformatted AHT, offshore raw ratios, the trend label, and the nested `identity` object are produced from those stored inputs. This regression does not walk every nested achievement key, and the digest does not claim a field that the payload above omits.

The HTTP lifecycle test sets `check_same_thread=False` on its own SQLite `StaticPool`, which is the TestClient thread requirement. Its actor is an injected `request.state.user`. The test comment records that this fixture identity leaves product auth unchanged. Real JWT evidence stays with the reviewer.

`EmployeeProfileView` reads summary records and legacy performance data. `useEmployeeProfile` is a separate helper and is currently unused by that view. Committed invalidation still omits `['employee']`, `['planning']`, and `['corrective-actions']`, and report prefixes stay on `['reports', 'center']`. That omission is not acceptance of a stale profile score. Saved story drafts, plans, and human-authored actions stay outside the committed refresh. Successful apply and rollback call `refreshPerformanceData`. Approve, and a failed apply, leave that refresh uncalled.

Paths: `Backend/api/dependencies.py`, `Backend/tests/test_serialization_cache_identity.py`, `Frontend/src/components/settings/monthlyCorrection.ts`, `monthlyCorrection.test.ts`, `committedEvidenceCache.test.tsx`, `EvaluationSettingsPanel.test.tsx`.

The reviewer probe `reviewer-serialization-identity-probe.py` was not executed again from this lane.

### Gates after these edits

Environment for backend commands: `APP_ENV=test`, `DATABASE_URL=sqlite:///:memory:`, empty `REDIS_URL`, `CI` unset, run from `Backend/` with `python -m pytest -q -p no:cacheprovider`. PostgreSQL was not assigned and was not run. No test was skipped, no assertion was weakened, and no bundle budget was raised.

| Gate | Result |
| --- | --- |
| Focused backend `test_serialization_cache_identity.py` and `test_evaluation_cache_identity.py` | 5 passed, 8 warnings, 5.29s, exit 0 |
| Focused frontend vitest: pinned basis, monthly correction, both committed-evidence files, evaluation settings panel, `--maxWorkers=2` | 5 files, 42 passed, duration 7.03s, tests 2.83s, exit 0 |
| Frontend `tsc -b --pretty false` after the optional-unit call sites were typed | Exit 0. An earlier typecheck in the same turn failed on those call sites and does not count |
| Frontend `eslint .`, then `vitest run --maxWorkers=2`, then `build:ci` | One command, exit 0, duration 153.83s. ESLint completed. Vitest: 96 files, 724 passed, duration 121.31s, tests 71.02s. Vite build 1.65s. Bundle budgets passed |
| Backend full pytest | Exit 1. 1152 passed, 1 failed, 1 skipped, 63 warnings, 170.63s. The failure is `tests/test_marketing_import.py::test_real_marketing_workbook_imports_with_incomplete_rows_excluded`: `result.report["total_rows"]` is 131 where the test expects 68. The workbook was left unchanged |
| `graphify update .` | Exit 0, 55.46s. 9535 nodes, 25953 edges, 418 communities. `graphify label` was not run |

The earlier frontend count of 719 passed / 94 files and the earlier backend count of 1149 passed belong to the previous lane. They do not cover this follow-up. The 724 / 96 and 1152 counts above are the runs that include it.

Bundle budget lines from that `build:ci`: BarChart 16.20/5.64, CartesianChart 324.81/95.16, GradeDistributionChart 2.65/1.16, LineChart 21.29/6.25, charts runtime aggregate 364.95/108.21, animation 129.19/41.86, TeamDashboardView 139.51/35.74 kB raw/gzip. Vite also reported `index-BE9nq0jX.js` at 512.48 kB / gzip 153.62 kB. The existing chunk-size warning stayed, and the budget check passed.

### Still not run

| Check | Status |
| --- | --- |
| Reviewer `reviewer-evaluation-aggregation-probe.mjs` `--mixed-unit-key` and `--mixed-key` on this worktree | Not run here. Reviewer owns the harness |
| Reviewer `reviewer-serialization-identity-probe.py` | Not run here. Reviewer owns the harness |
| Reviewer repeat of the real-JWT browser workflow after these edits (same client, fresh client, rollback, six live API families) | Not run here. The earlier scratch-fixture pass is reviewer-owned and is not full acceptance |
| `EmployeeProfileView` in a browser | Not run. The unused `useEmployeeProfile` helper is not that acceptance |
| PostgreSQL, browser widths and themes, performance lane, all-pages acceptance | Not run |
| Commit, push, merge, main publication, deployment | Not done |

## Executive percent display and direct mixed actual

Scoped Outbound attendance is stored as a ratio. August actual `0.4607` and target `0.65` are `46.1%` and `65%`. July actual `0.4` against the same target makes the raw gap `+6.1%`. `fmtKpiValue` and `fmtKpiDelta` already treat `%` as percent points. `kpiRows` was rounding the ratio to two digits first, so `0.4607` became `0.46` and the tables rendered `0.5%` / `0.7%`.

The scale is applied inside `kpiRows`, one stored actual/target pair at a time, before that rounding. It uses the existing paired-target rule: a `%` target in `(0, 1]` is a ratio, and `1` means `100%`. A percent-point target stays stored, so `0.1` against `5` remains `0.1%` and `88` against `90` remains `88%` / `90%`. `1.077` against `1` becomes `107.7%` / `100%`. Lower-better gaps use the same scaled values, so abandon `0.08` against `0.05` displays `8%` / `5%` with a direction-adjusted gap of `−3%` and a month change of `−4%`. Seconds and counts are not scaled. Achievement ratios and official scores, caps, and grades are unchanged. Weights stay fractions; the table still prints a weight of `0.6` as `60%`.

Insight-workspace drivers that already carry percent-point `current_value` do not pass through `kpiRows`, so this does not rescale them. Function attention, the function KPI table, and both function and corporate driver cards read the composed fields.

`aggregateConfiguredTeamKpis` now leaves `actual` as `NaN` when pinned units or pinned keys disagree. Same-unit target or direction variation still publishes the pooled actual, including the geo ratio `0.5` for the synthetic Outbound attendance counters. Cohort scores are unchanged. The uniform pooled contribution remains `35.714285714285715`.

Tracked regression: `Frontend/src/components/executive/v1/executivePercentDisplay.test.tsx` maps synthetic scoped rows through `mapScopedPerformanceRecord`, `toExecRecords`, and `composeExecutiveSummary`, then renders `TeamKpiTable`, `TeamsNeedingAttentionCard`, and both driver cards. The direct-aggregate order checks are in `teamKpiAggregator.pinnedBasis.test.ts`.

Reviewer probes run read-only against this worktree, exit 0:

- `reviewer-executive-percent-probe.mjs`: actual `46.1%`, target `65%`, change `+6.1%`, composed actual `46.07`.
- `reviewer-evaluation-aggregation-probe.mjs --mixed-unit-key --direct-mixed-actual`: both orders, unit `count` and key `Distinct Attendance`, direct actual unavailable, `basisVaries` true, uniform pooled contribution `35.714285714285715`.

### Gates for this follow-up

| Gate | Result |
| --- | --- |
| Focused vitest: executive percent display, compose, pinned basis | 3 files, 50 passed, 3.48s, exit 0 |
| Frontend `vitest run --maxWorkers=2`, then ESLint, `tsc -b`, `build:ci` | One command, exit 0, 193.20s. Vitest 97 files, 725 passed, duration 151.35s. Bundle budgets passed |
| Backend pytest, same test environment as the previous lane | Exit 1. 1152 passed, 1 failed, 1 skipped, 63 warnings, 218.88s. The failure is still `131 == 68` in `test_real_marketing_workbook_imports_with_incomplete_rows_excluded` |
| `graphify update .` | Exit 0, 68.25s. 9547 nodes, 25986 edges, 418 communities. Labeling was not run |

### Still not run after this follow-up

| Check | Status |
| --- | --- |
| Reviewer browser revisit of the real Function KPI table, attention detail, and Departmental drivers | Not run here |
| PostgreSQL, browser widths and themes, performance lane, all-pages acceptance, `EmployeeProfileView` | Not run |
| Commit, push, merge, main publication, deployment | Not done |

## Small canonical contribution display

A pinned Outbound attendance row with actual `0.01`, applied target `0.7`, and weight `0.5` has canonical team contribution `(0.01 / 0.7) * 0.5 * 100` = `0.7142857142857143` score points. The stored KPI contribution on the record stays the unscaled fraction `(0.01 / 0.7) * 0.5`. Raw `T.Attend%` stays `0.65`. The applied target stays `0.7` and the applied weight stays `0.5`. Pooling, caps, grades, and Marketing aggregation are unchanged.

`calculateAggregatedTeamPerformance` already publishes that value as score points. `getKPIsForAgent` does the same for persisted rows by multiplying the stored fraction by 100 once. Marketing `averageContribution` is already `achievement ratio * weight * 100`. Design System passes `30`. Existing card tests pass `24.3`, `40`, `20`, `0`, and `35.5` as points. No caller of `PerformanceKpiCard` still supplies a 0–1 fraction.

The cards treated any contribution at or below 1 as a fraction and multiplied by 100 again. `0.7142857142857143` became `71.4`, then the weight cap of `50` clamped the Patient Attendance card to the full weight.

Measured on `reviewer-small-contribution-probe.mjs` against this worktree, read-only:

| | Canonical contribution | Rendered Patient Attendance card |
| --- | --- | --- |
| Before | `0.7142857142857143` | `Contribution50.0%` / `Weight50%` (probe exit 1) |
| After | `0.7142857142857143` | `Contribution0.7%` / `Weight50%` (probe exit 0) |

The same score-point contract now applies in both display sites. `TeamKpiSection.calcContribution` passes an aggregate contribution through, including `0` and values below `1`, and still caps it at the KPI weight. `PerformanceKpiCard` does the same. A missing aggregate contribution still uses the existing actual/target fallback, which already returns score points. A varied basis still renders `Contribution—` and `Weight—`. Zero stays `Contribution0.0%`. Exactly one point stays `Contribution1.0%`. An ordinary contribution above one point stays on that scale: attendance `(0.5 / 0.7) * 0.5 * 100` renders `35.7%` with weight `50%`, and pinned Productivity `(0.7780694444444445 / 0.8) * 0.2 * 100` (`19.451736111111112`) renders `19.5%` with weight `20%`. A sub-one Productivity point (`0.004 / 0.8 * 0.2 * 100` = `0.1`) renders `Contribution0.1%` / `Weight20%`.

Tracked coverage: `PerformanceKpiCard.test.tsx` adds the sub-one, exactly-one, and zero card cases and keeps the original `24.3`, `40`, `20`, `0`, and `35.5` assertions. `TeamKpiSection.contributionDisplay.test.tsx` maps synthetic scoped rows through `mapScopedPerformanceRecord`, the real Outbound file, and `calculateAggregatedTeamPerformance`, then renders `TeamKpiSection`.

### Gates for this follow-up

| Gate | Result |
| --- | --- |
| Focused vitest: shared card, new pipeline regression, existing `TeamKpiSection` | 3 files, 30 passed, 3.48s, exit 0 |
| Reviewer `reviewer-small-contribution-probe.mjs` | Exit 0. Card text `Contribution0.7%` / `Weight50%`. Canonical contribution unchanged |
| Frontend `vitest run --maxWorkers=2`, then ESLint, `tsc -b`, `build:ci` | One command, exit 0, 185.23s. Vitest 98 files, 733 passed, duration 132.78s. Lint, typecheck, and `build:ci` exit 0. Bundle budgets passed. `TeamDashboardView` 139.07 kB raw / 35.59 kB gzip. Index chunk 512.58 kB / gzip 153.66 kB |
| Backend pytest, `APP_ENV=test`, `DATABASE_URL=sqlite:///:memory:`, empty `REDIS_URL`, `CI` unset | Exit 1. 1152 passed, 1 failed, 1 skipped, 63 warnings, 232.40s. The failure is still `131 == 68` in `test_real_marketing_workbook_imports_with_incomplete_rows_excluded` |
| `graphify update .` | Exit 0, 65.49s. 9554 nodes, 26005 edges, 420 communities. Labeling was not run |

### Still not run after this follow-up

| Check | Status |
| --- | --- |
| Browser walk of Team Dashboard, Marketing position cards, and the design-system card | Not run. The SSR probe and React tests are not that acceptance |
| PostgreSQL, real JWT, browser widths and themes, performance lane, all-pages acceptance | Not run |
| Commit, push, merge, main publication, deployment | Not done |

## API insight driver percent display

Function Summary and Departmental Summary driver cards take Insights API rows through `mapDrivers` when the page is not building drivers from scoped performance records. `kpiRows` and `scopedRecordDrivers` already turn a paired ratio into percent points. API `InsightDetail` keeps the raw measure: `current_value`, `previous_value`, `target_value`, `gap_value`, `change_value`, and `raw_change` share the KPI unit. For a `%` (or `percent` / `percentage`) target in `(0, 1]`, that unit is a ratio. `achievement_percent`, `impact_points`, weighted-gap points, and contribution-change points are already score points. The backend explanation text is already written in percent points. The builder and the stored payload stay on that contract.

`mapDrivers` used to copy those detail numbers straight onto the executive driver. `fmtKpiValue` and `fmtKpiDelta` then rounded them as percent points. A reviewer Function Summary DriversCard therefore showed Attendance `0.5%` and raw change `−0.1%` beside impact `−8.51%`, and Booking `0.3%` and raw change `+0.1%` beside impact `+4.32%`. The same payload's explanation already said Attendance `46.1%`, previous `55.3%`, target `65.0%`, and raw change `−9.2%`.

Anonymous API numbers behind that card:

| Driver | Current | Previous | Target | Raw change | Gap | Achievement | Impact points |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Attendance | `0.4607` | `0.5529` | `0.65` | `-0.0922` | `-0.1893` | `70.88` | `-8.51` |
| Booking | `0.3008` | `0.1704` | `0.3` | `0.1304` | `0.0008` | `100` | `4.32` |

`fmtKpiValue(0.4607, '%')` is `0.5%`. `fmtKpiDelta(-0.0922, '%')` is `−0.1%`. Booking `0.3008` displays `0.3%` and `0.1304` displays `+0.1%`.

The new-entry branch of `mapDrivers` now runs `executivePercentValue` on current, previous, raw change, change, and gap, using that detail's unit and target, before any display rounding. When `raw_change` is absent and both endpoints are finite, the existing fallback still subtracts the unscaled previous from the unscaled current, and that difference is scaled once. Impact, weighted gap, contribution change, achievement percent, and weight stay exact. Ranking still orders those impact points. Formatters stay global percent-point formatters. `scopedRecordDrivers` stays on the `kpiRows` scale, so a record-derived `0.4607` attendance driver stays near `46.07`.

Composed display values, then the real `DriversCard` text:

| Driver | Composed current / raw change | Card |
| --- | --- | --- |
| Attendance | `46.07` / `-9.22` (previous `55.29`, gap `-18.93`) | `46.1%`, `−9.2%`, impact `−8.51%` |
| Booking | `30.08` / `13.04` (previous `17.04`) | `30.1%`, `+13%`, impact `+4.32%` |

`fmtKpiDelta` prints `Number(abs.toFixed(1))`, so Booking's `13.04` point change renders `+13%`. Attendance's decline renders with the formatter's unicode minus. Function and corporate compositions keep the same ranking: the more negative impact is first.

The same regression keeps the other scales. Quality `88` against target `90` stays `88%`. Rework `0.1` against target `5` stays `0.1%`. Conversion `1.077` against target `1` becomes `107.7%`. Seconds, counts, and currency stay stored; `2500` AED still renders `AED 2.5K`. A `%` value with no target stays `0.46`, and a missing raw change falls back to the unscaled difference `0.06`. Explicit nulls stay null. Fixture drivers that omit `target_value` keep their stored percent points, including the existing compose ranking and `raw_change: 1.6`.

Tracked file: `Frontend/src/components/executive/v1/apiDriverPercentDisplay.test.tsx`. It builds an anonymous API-shaped fixture, runs `composeExecutiveSummary` for the function view and the corporate view, and renders `DriversCard`. Counter-cases call `mapDrivers` directly. The record-derived lock calls `scopedRecordDrivers`. Existing assertions in `compose.test.ts` and `executivePercentDisplay.test.tsx` stay.

Path changed for the display boundary: `Frontend/src/features/executive/compose.ts` (`mapDrivers` only). The removed backend `_kpi_field` helper stays removed.

### Gates for this follow-up

| Gate | Result |
| --- | --- |
| Focused vitest after the title type fix: API driver display, executive percent display, compose | 3 files, 39 passed, 5.51s, exit 0 |
| Frontend `vitest run --maxWorkers=2`, then ESLint, `tsc -b`, `build:ci` | One command, wall 170.97s, overall exit 2. Vitest exit 0: 99 files, 736 passed, duration 128.90s. ESLint exit 0. First `tsc -b` exit 2: `apiDriverPercentDisplay.test.tsx` line 16, `TS2322`, `title` received `kpi_key` as `string \| null`. `build:ci` exit 0. Bundle budgets passed. `TeamDashboardView` 139.07 kB raw / 35.59 kB gzip. Index chunk 512.58 kB / gzip 153.66 kB |
| `tsc -b` again after `title: patch.kpi_key ?? patch.id` | Exit 0. Every fixture in that file already passes a string `kpi_key`, so the card assertions are unchanged. The focused vitest above re-ran that file |
| Backend pytest, `APP_ENV=test`, `DATABASE_URL=sqlite:///:memory:`, empty `REDIS_URL`, `CI` unset | Exit 1. 1152 passed, 1 failed, 1 skipped, 63 warnings, 205.09s. The failure is still `131 == 68` in `test_real_marketing_workbook_imports_with_incomplete_rows_excluded` |
| `graphify update .` after the `mapDrivers` edit | Exit 0, 73.00s. 9566 nodes, 26030 edges, 414 communities. Labeling was not run |
| `graphify update .` after the title line | Exit 0, 37.34s. No topology change; graph outputs left untouched. Labeling was not run |

### Still not run after this follow-up

| Check | Status |
| --- | --- |
| Reviewer repeat of the real-JWT Function Summary and Departmental Summary driver cards | Not run here. The React `DriversCard` assertions cover the composed text. They are not that browser repeat |
| PostgreSQL, browser widths and themes, performance lane, all-pages acceptance | Not run |
| Commit, push, merge, main publication, deployment | Not done |
