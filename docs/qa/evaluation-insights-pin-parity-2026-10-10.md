# Insights persisted pin parity — bounded QA lane

Date: 2026-10-10. Branch: `codex/evaluation-insights-pin-parity`. Base: `625abf4` (`Bound serialized revision retention with fair expiry cleanup`). No commit, push, merge, deploy, reset, production database write, credential change, or private-workbook edit.

This is a bounded local checkpoint for one missing Insights link. It is not production release approval, and it is not a claim that Phase 5 or every team is complete. Families that still have no accepted golden stay locked.

## Defect

`InsightsService._configured_kpi_values` dropped a persisted KPI key that was absent from the technical static file whenever that file existed. August Outbound Productivity is a trusted monthly pin and is absent from `Backend/config/teams/outbound.json`. `_persisted_kpi_item` copied optional metadata for an object-shaped KPI but did not copy `evaluation_pinned`, so a canonical object lost the pin before the key check.

Reproduced before the fix, same new tests, `APP_ENV=test`, `DATABASE_URL=sqlite:///:memory:`, `REDIS_URL` empty, `CI` unset: **10 failed, 2 passed** in 6.57s. The two that already passed were the unpinned exclusion / file-ratio mean, and the same-direction cross-month comparison. The failures were: unknown pinned Productivity raised `KeyError`; malformed pin flags kept a stored `lower_better` on Attendance; an object pin omitted Productivity from options; a pinned multi-row Attendance rollup stayed on the file ratio mean `0.60` instead of `0.70`; a cross-month direction change was still scored as `higher_better`; after a real apply, August options were only Attendance, Booking, Other, Quality, `aht`, and `no_show_rate`.

## What changed

Production change is only `Backend/services/insights_service.py`.

- A KPI is trusted only when `evaluation_pinned is True` after it has already been serialized. The string `"true"`, `"True"`, `1`, a truthy object, and a missing flag are not trusted. A malformed flag is removed before the legacy direction resolver, so `bool("true")` cannot select a pinned direction.
- A trusted pin keeps its stored identity, actual, target, weight, direction, unit, achievement, and contribution, including a key that is not in the static file. The static file is not overlaid, and the legacy achievement clamp and contribution scale are not applied to that row. Label is filled from the key only when the stored label is empty. Direction is normalized in place and marked `direction_source="pinned"` only when normalization succeeds.
- Unknown or unpinned stale keys stay excluded when a technical static config exists. Legacy unpinned rows still receive the file direction, unit, aggregation, weight fallback, and the existing clamp.
- Dict rows were already copied wholesale. Object rows now copy `evaluation_pinned` only when the attribute is present. A raw ORM `KPIValue` has no such attribute. A parent `evaluation_basis` or a sibling dict does not bless that object. Insights does not read `record_payload` as a second trust source. The existing server contract remains `DashboardRecordService._pinned_schema_record`, which sets `"evaluation_pinned": True` only for a payload whose `evaluation_basis.pinned` is set.
- Driver, overview, and trend cohorts now include direction and unit. Two rows with the same key but a different direction or unit are not averaged and do not use each other as the previous value. The same direction and unit still compare across months when only weight or target differs. `InsightKpiTrend` still has one unit and one direction because the existing chart scales every point with that unit. A historical point whose unit differs from that chart unit, and every raw point when the selected month itself mixes units, is published with actual, target, and chart status empty. Its period achievement percentage can remain. A same-unit direction change keeps the scaled raw points and each period's achievement, and it does not compute a movement across the boundary. An empty selected month still falls back to the newest uniform month in the six-month window.
- KPI narrative ids stay on the legacy type/title/scope/key identity when that id is already unique. When separated cohorts share one narrative, the id gains direction, unit, and variant. Driver ids already include the cohort key. `insight_id` is assigned after that disambiguation, so a driver still points at its own row.
- Trusted pins do not inherit the static aggregation method. A multi-row pinned Attendance rollup therefore uses the default weighted average. Unpinned rows still use the Outbound file ratio mean. `aggregate_kpi_metric` was not rewritten. The driver publication threshold was not changed. August Productivity's gap stays below `0.5`, so this lane asserts it in options, overview counts, the selected KPI trend, and `team_analyses`.

`dashboard_record_service.py`, `reporting_evidence_service.py`, `utils/kpi_direction.py`, `outbound.json`, evaluation workflow, scoring, auth, RLS, and the frontend were not edited. Reporting already keeps an unknown KPI when `evaluation_pinned is True`.

## Decisions held

- D001: settings stay admin-only. This lane does not add a settings grant. Ordinary Insights reads use the existing scope filter.
- D002: unadmitted families stay locked. No new family was admitted, and no blocked-family golden was invented.
- D003: a new upload conflict still blocks. This lane does not change conflict policy. A fixed target that the existing apply path stores is shown as stored; the workbook source evidence is left as stored.
- D004: July remains four KPIs with Attendance weight 70%. August adds Productivity at weight 10% and Attendance at weight 60%. Both months' Attendance workbook target stays 0.65. The Productivity workbook target is 0.8. Productivity is not inferred from Available Time.
- D005: only an explicit apply or rollback changes the stored basis. Opening a draft, and a refused edit, do not. Rollback restores the prior applied snapshot and does not rescore the pin on read.
- Outbound capability still refuses a canonical scored key whose direction is not `higher_better`. The workflow test expects that refusal (`Attendance must stay higher-is-better`) and then applies a legal edit: Attendance weight 0.50, fixed target 0.70, Booking weight 0.20 so the weights still sum to 1. A stored `lower_better` pin is covered on the Insights read path with a synthetic exact `True` flag, not by weakening the capability check.

## Verification

Environment for every pytest process: `APP_ENV=test`, `DATABASE_URL=sqlite:///:memory:`, `REDIS_URL` empty before imports, `CI` unset, `PYTHONPATH` set to `Backend`, pytest cache plugin disabled. No PostgreSQL schema reset. No private-workbook test. No Marketing workbook test.

Focused Insights, reporting, and evaluation modules, after the reviewer delta, JUnit `tests=282 failures=0 errors=0 skipped=0 time=51.941`:

| Module | Tests |
| --- | ---: |
| `test_insights_persisted_pin_parity.py` | 16 |
| `test_insights_service.py` | 40 |
| `test_insights_direction.py` | 12 |
| `test_insights_overall_trend.py` | 21 |
| `test_insights_report_service.py` | 21 |
| `test_reporting_applied_employee_basis.py` | 4 |
| `test_reporting_evidence_service.py` | 19 |
| `test_reporting_basis_annotation.py` | 3 |
| `test_report_service.py` | 23 |
| `test_report_story_service.py` | 20 |
| `test_reports_center_service.py` | 5 |
| `test_evaluation_workflow_consumer.py` | 7 |
| `test_evaluation_period_integration.py` | 24 |
| `test_evaluation_month_revision.py` | 15 |
| `test_evaluation_outbound_productivity_golden.py` | 9 |
| `test_outbound_productivity_ingestion.py` | 8 |
| `test_monthly_evaluation.py` | 5 |
| `test_evaluation_safety.py` | 10 |
| `test_evaluation_json_safety.py` | 5 |
| `test_evaluation_revision_actor_guard.py` | 5 |
| `test_evaluation_consumer_review_guard.py` | 3 |
| `test_evaluation_history_integrity.py` | 2 |
| `test_evaluation_cache_identity.py` | 2 |
| `test_evaluation_saved_pin_guard.py` | 2 |
| `test_evaluation_upload_cache_identity.py` | 1 |

The new file is included in that 282. It is not only a `_configured_kpi_values` helper check. `test_apply_and_rollback_round_trip_the_pinned_basis_through_insights` uses an in-memory SQLite `EvaluationWorkflow` plus `DashboardRecordService` and `InsightsService.generate_workspace`.

Reviewer delta, same file: a July percent actual is not plotted as a count under an August count chart, and its change is empty. A mixed August unit leaves the chart unit empty and does not plot the July percent actual or target; July achievement `50.0` remains and its chart status is empty. A same-unit direction change keeps July `0.40` / `0.80` and August `0.20`, with August `change_value` empty. Three Attendance cohorts that share one title have three item ids, three driver ids, and matching `insight_id` links. `git diff --check` on the touched files reported no whitespace errors.

Observed on that round trip:

- Before apply, August Insights options do not contain Productivity, even if the raw row carries the actual. July is not applied and does not gain Productivity. The July SQL score stays at the fixture's initial score.
- Default August apply stores score `79.82`. The team summary current score is `79.8`. Insights options include Productivity. Overview counts are August 5 and July 4. The Productivity trend point uses the stored KPI actual, which the fixture quantizes to 4 decimal places (`0.7781`). `raw_data["Productivity"]` stays the full workbook golden. Target stays `0.8`, direction `higher_better`, weight text `10.0%`.
- An Outbound manager and employee `ANON-1` see that Productivity inside their existing scope. A Sales manager does not, and requesting team Outbound raises. Employee `ANON-2` does not see `ANON-1`. No extra grant was added.
- The illegal Attendance `lower_better` edit is refused before a snapshot write. The legal weight and fixed-target edit is what Insights shows (`higher_better`, target `0.70`, weight `50.0%`). Source evidence Attendance target stays `"0.65"`. Raw data is unchanged.
- Rollback restores the first applied score `79.82`, Attendance target `0.65`, weight `60.0%`, direction `higher_better`, and the Productivity pin. July still has no Productivity.

Synthetic cases in the same file: exact `True` keeps unknown Productivity and an edited Attendance target, weight, direction, achievement `1.2`, and contribution `0.72` with no file aggregation; malformed flags exclude Productivity and put Attendance back on the file `higher_better` path with contribution clamped to the weight; an object pin matches the dict pin; a parent pin claim does not bless an object that lacks the attribute; pinned multi-row Attendance current value is `0.70`; the same month with opposite directions is two analyses and the trend actual is empty; a direction change across months does not reuse the other month as `previous_value`; the same direction and unit still compare.

`graphify update .` completed with no LLM call: 9652 nodes, 26317 edges, 435 communities. Empty JSON-node and missing `tree_sitter_sql` warnings remain. `graphify-out/` is gitignored. `tree_sitter_sql` was not installed.

## Not run, and not waived

Independent reviewer follow-up (10 October): the source diff and all new regressions were reviewed after the delegate stopped. The previously RED trusted-Productivity probe now passes. The reviewer separately executed the complete 25-module focused gate listed above: **282 passed, 8 warnings / 65.06s**, with no exclusions of cases inside that gate. This accepts only the bounded Insights slice. Main publication and full integrated release remain unauthorized/unverified; the full-suite Marketing failure is still a release issue.

- The full backend suite was not run. The known Marketing workbook failure, 131 available rows versus the asserted 68 in `test_real_marketing_workbook_imports_with_incomplete_rows_excluded`, was not re-run and is not waived. No fixture, skip, or expectation was changed to hide it.
- The KPI trend response still has one global unit and direction. Incompatible history is a gap on that chart. Per-point units were not added to the public schema, and the frontend scaler was not changed.
- PostgreSQL schema reset, migration checks, and `evaluation_*_pg_checks.py` were not run.
- Private workbooks were not opened or edited.
- No browser, JWT, or frontend pass. This lane does not change UI.
- No RLS, schema, formula, or cache redesign.
- The shared direction resolver still logs `KPI direction unresolved for team='Outbound' kpi='productivity'` on the legacy dashboard path. That warning was captured on the pre-fix workflow run. `utils/kpi_direction.py` was left unchanged because the Insights retain path does not use that bool pin, and the focused suite passed without editing it.
- Blocked families still have no reviewer golden. They stay blocked.
