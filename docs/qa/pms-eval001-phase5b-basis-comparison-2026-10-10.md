# PMS-EVAL001 Phase 5B — scoring-basis comparison

Date: 2026-10-10. Worktree: `C:\Users\sghd70204\.codex\worktrees\evaluation-basis-comparison-notes\PMS_Dashboard`. Branch: `codex/evaluation-basis-comparison-notes`. No commit, push, merge, deploy, or other worktree edit. Phase 7 durable-job paths were not opened. Anonymous in-memory SQLite only.

This is not a claim that the evaluation roadmap is complete. Marketing, Pharmacy, CSR, IP Final, Managerial, and Corporate goldens stay blocked. The known Marketing workbook expectation (131 vs 68) was not run and is not green.

## What the comparison says

`compare_scoring_basis` reads pinned KPI rows already on the records it is given. A version id or rules checksum alone is not a rule change. `0.65` and `65` stay different. Scores, directions, units, cohort ids, and July-without-invented-Productivity behavior are unchanged.

- A team and level present on only one side is a population-coverage change. It does not invent rules for the missing scope. The aggregate is not like-for-like, and raw performance is not reported as simply unchanged or changed. The message says the population changed and that some actuals are not comparable.
- A blank position is a valid team-scope identity. Coding / Employee / blank position can be like-for-like. That same blank position is not grouped with position `Agent`.
- A row with a blank team or level is not a trusted scope. If every row lacks a trustworthy team and level, the state stays `unknown` and like-for-like is false. If a trusted shared scope also exists, the invalid row is not dropped: like-for-like is false and raw performance is not `unchanged`.
- When source, formula, or aggregation is explicit on both sides and differs, the state can be `changed`, but the stored actuals are not treated as comparable raw evidence. The message does not say comparable raw performance is unchanged.
- One-sided source, formula, or aggregation stays `unknown`. Both absent stays comparable.
- A target or weight change with the same explicit evidence can still say comparable raw performance is unchanged.

## Consumers that actually render or return it

- Insights workspace: executive story, six-month trend points, team summaries, and a separate `basis_note` on non-data-quality items. One local period/scope index is built from the already filtered records for that call. Exact previous calendar month only. No new query and no process-wide cache.
- Legacy `GET /api/performance/insights` adds at most one warning when the current records share one year and a team comparison is changed, mixed, or unknown.
- Executive and Function summaries attach `basis_context` in `compose.ts` against the exact previous calendar month. Score deltas still use the latest earlier period. Visible notes: Teams at Risk, score trend, Function cards, Insights executive summary, performance trend, insight drawer ("Evaluation settings", outside data-quality), teams needing attention, and the Team Risk Matrix.
- The executive score trend and the Insights performance trend keep one persistent note: the latest point's message. A focused or hovered month shows that month's own message in the tooltip, without a second `basis-comparison-note` id. An older missing-previous-month note does not replace a current unchanged comparison. Chart hover, keyboard, empty, gap, and geometry behaviour were not retuned. Team and function banners still join the visible team or function messages; those are not month series.

## Reporting inspection

`movement()` and `trend()` still set `scoring_basis_changed`, `basis_changed`, `basis_state`, and the existing narratives from the old signature (KPI key, weight, target, direction, unit). `basis_context` is an extra key. Version identity is not an input to either path. Unpinned rows can keep `scoring_basis_changed: true` while `basis_context.state` is `unknown`. No narrative, reconciliation boolean, or saved-report bytes were rewritten.

`BlockRenderer` now reads `basis_context` when a fresh payload includes it. The shared note shows `context.message`, and that context replaces the unqualified "Scoring basis changed", "Raw performance changed", "Basis changed", and "Mixed basis" labels. Trend points are period-labelled (`July 2026: …`) so an older missing-month note is not presented as the current comparison. Payloads that omit `basis_context` keep the previous badges. An explicit source or formula difference can therefore be visible in the note while the old boolean stays false.

## Planning

`PlanningService.classification_basis_context` was removed. It had no production caller, and adding a year argument to `GET /api/performance/planning` would have been a new classification surface. Classification stability is now asserted by calling `classify_records` before and after `compare_adjacent_records`: the Attrition Risk and Reward Candidate membership stays the same, and the adjacent comparison still reports changed versus unchanged rules.

The note that users can see is additive `basis_note` on each resolved item in the existing plan-detail `linked_insights` list. `PlanningService.get` already loads access-scoped Insights through `generate_workspace` and previously dropped `detail.basis_note` in `model_dump`. The same dump now includes that one field. Unresolved links stay `{id, resolved: false}` and do not invent a note. `PlanningView` renders the note in Linked evidence. Saved baseline, target, current, and status are not rewritten. No new endpoint or record fetch was added. `GET /api/planning/{plan_id}` is a wrapper around `PlanningService.get`; the service read was tested, and the HTTP wrapper was not called separately.

## Gates

Environment before imports: `APP_ENV=test`, `DATABASE_URL=sqlite:///:memory:`, `REDIS_URL` empty, `CI` unset. Commands were prefixed with `rtk`. No PostgreSQL. No live browser; component tests under jsdom are the substitute.

Focused Python, 26 modules, final tree:

`test_evaluation_cache_identity.py`, `test_evaluation_consumer_review_guard.py`, `test_evaluation_history_integrity.py`, `test_evaluation_json_safety.py`, `test_evaluation_month_revision.py`, `test_evaluation_outbound_productivity_golden.py`, `test_evaluation_period_integration.py`, `test_evaluation_revision_actor_guard.py`, `test_evaluation_safety.py`, `test_evaluation_saved_pin_guard.py`, `test_evaluation_upload_cache_identity.py`, `test_evaluation_workflow_consumer.py`, `test_insights_basis_context.py`, `test_insights_direction.py`, `test_insights_overall_trend.py`, `test_insights_persisted_pin_parity.py`, `test_insights_report_service.py`, `test_insights_service.py`, `test_planning_workspace.py`, `test_report_service.py`, `test_report_story_service.py`, `test_reporting_applied_employee_basis.py`, `test_reporting_basis_annotation.py`, `test_reporting_evidence_service.py`, `test_reports_center_service.py`, `test_scoring_basis_comparison.py`.

Result after this delta: **313 passed, 8 warnings, 47.79s, exit 0**. The four additions inside that run are the blank-position scope, the extra invalid-scope row, and the two saved-plan reads. `test_marketing_import.py` was not in this run.

The external probe file `D:\Projects\PMS_Dashboard\tmp\reviewer-basis-scope-20261010.py` was run unchanged with the same environment, together with the basis and planning workspace modules: **43 passed, 4.64s, exit 0**. Those 43 include the probe's two tests.

Frontend Vitest, project config, jsdom: helper, `compose.test.ts`, Teams at Risk, score trend, Function cards, insight drawer, Insights view, report block renderer, Planning view, and the Insights performance-trend note. **10 files, 155 passed, exit 0**.

`npm run typecheck` (`tsc -b --pretty false`): **exit 0**.

ESLint on the changed frontend files: **exit 0**.

`npm run build:ci`: **exit 0**. Vite built. `Bundle budgets passed.`

## Not run

- Marketing workbook test (131 vs 68).
- PostgreSQL, live databases, and private employee data.
- A live browser pass. Plan, report, and chart behaviour was checked in jsdom.
- The FastAPI wrapper `GET /api/planning/{plan_id}` itself. The service read it calls was tested.
- `GET /api/performance/planning` still has no year and no classification note. No classification page was added.
- Settings editor, `models.py`, migrations, scoring, upload, permissions, and saved report bytes.
- Phase 7 worker, schema, workflow apply, settings panel, and cache.
- Missing family goldens.

## Independent reviewer gate — 10 October, supersedes candidate-only evidence above

The implementer was stopped before reviewer edits. The actual `/executive` route intentionally renders the pre-v1 overview; annotating v1 components alone did not cover it. The reviewer added optional typed `basis_context` to the existing summary API/hook and an additive note to that real overview. Already access-scoped scalar summary rows are reused. Only pinned rows from the exact current and adjacent calendar months read persisted KPI scalar evidence in batches of at most500 record/year keys; no employee/roster reload, score recomputation, N+1, or raw source rewrite. A hoisted payload index prevents quadratic matching. Numeric older-period fallback remains unchanged; the basis note never silently compares that older month. The summary cache identity was versioned for the additive contract.

Added two scope/calendar/no-roster-hydration regressions, a real persisted-pin parity/one-KPI-query regression, and an Executive note/numeric-preservation test. The persisted-pin fixture initially omitted child evidence and correctly returned unknown; it was supplied the normal stored evidence, not given weaker expectations. The existing Departmental permission-note test now selects its exact note rather than assuming there can only be one `role=note`; all scope/permission assertions remain. Actual mobile testing also found the existing Geography196px+104px fixed row escaping375px. A shrinking/stacking grid fixes that without suppressing content or adding page overflow clipping.

Final full normal backend including the two external scope probes: **1219 passed, one known Marketing131-vs68 failure, one existing skip,63 warnings,264.03s, exit1**. No exclusions, expectation change, or failure waiver. The slice is not a fully green release.

Final full frontend: **761 passed,102 files,186.43s, exit0**, maxWorkers2, no skips/retries/timeouts changed. Full lint, typecheck, production build and bundle budgets passed; existing canvas warnings and512.75kB main-chunk warning remain. These suite times are not a production latency claim.

Real HTTP/JWT and Chromium gate passed on a fresh reviewer-owned anonymous SQLite fixture at8319 and Vite5319 only. July/August approvals left ALL stored performance/KPI row bytes unchanged. Explicit Apply produced82.85/79.82, preserved original raw data, and kept Productivity August-only. Performance Team/Function Director received403 for monthly management. Actual Planning POST+GET carries the linked basis note while human baseline60/target80/current70/Draft remain unchanged. A fresh Story template/draft/page API carries changed basis context and79.82/82.85 movement values. Existing generated report bytes remain covered by the unchanged full backend tests; browser validation creates only anonymous fresh drafts, not production reports.

Six actual routes (`/executive`, `/departmental-summary`, Function, Insights, Planning and Report editor) were verified at375/746/1024/1440. Notes visible; no page errors, document or note overflow; performance records, plan summary and report definition unchanged after navigation. Raw proof and screenshots: `D:/Projects/PMS_Dashboard/tmp/reviewer-basis-browser-evidence-20261010/proof.json`. Initial approval harness used an August baseline captured before July Apply and was corrected to capture immediately before EACH approval; the all-column persisted-row invariant was never removed. An initial anonymous report fixture used invalid slot `main`; corrected to the registry's `full`, with validation unchanged.

AST-only graph refresh passed9832nodes/26831edges/409communities. Existing zero-node JSON, missing tree_sitter_sql and stale community-name warnings remain; no semantic/API refresh claimed. Separate user's QA dependency file remains SHA256a75ae0b19d069bb9c127312791e090fd1ed119131b5151f757dce1c9e5994f25. No main merge, external push/deploy, production DB, source workbook, public worker or permission expansion. This is local consumer-slice acceptance only; unsupported families and Phase7 runtime/recovery gates remain pending.
