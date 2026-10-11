# Monthly evaluation: preserve the operational upload contract

Date: 11 October 2026
Status: the three Grok implementation streams have finished and their reviewed code is composed locally on `codex/original-upload-review` at `a6181a0`. Independent combined verification is complete: 846 frontend tests pass; backend has 1473 passing tests, one unchanged local Marketing acceptance failure and one existing dataset skip. Type checking, lint, build and bundle budgets pass. This is not an all-green release, production rollout or complete all-team column mapping.

## Objective

Monthly evaluation settings must use the same KPI identities, display names, cleaned values and scoring behavior as the application's established Inbound/Outbound upload path. Changing a month's targets or weights must not introduce a different workbook format, a new KPI, or a different formula. Example workbooks supplied for discussion are not operational-source authority.

This plan precedes implementation, as requested. It supersedes the assumption that a reference workbook's July/August rules automatically apply to every upload for those dates. It does not retrospectively rewrite approved settings or published results.

## Confirmed audit findings

| Area | Evidence | Consequence |
| --- | --- | --- |
| Outbound cleaner | `Backend/Data_Cleaning_Teams/outbound.py::process_outbound` uses four achievement columns, with the existing June exception. | A five-KPI template is not equivalent to this path. |
| Outbound upload scoring | `Backend/services/kpi_service.py::calculate_performance` chooses `canonical_outbound_basis` from the row's Date. | July/August reference weights, target fallbacks, per-KPI caps and Productivity requirements can affect an upload without its source being identified. |
| Monthly draft baseline | `Backend/services/evaluation/catalog.py::_period_template` and `baseline_lines` substitute the calendar-specific lines and append AHT. | Draft contents can differ from the operational upload's KPI list. |
| Inbound processing | `Backend/Data_Cleaning_Teams/inbound.py::process_inbound` and the Inbound branch of `KPIService` preserve a UTZ/Abandon selection. | A generic fixed-direction target-ratio contract cannot represent every row unchanged. |
| Capability boundary | `Backend/services/evaluation/capabilities.py` admits the reference Outbound months but not Inbound. | Simply removing a disabled state would permit an unproven calculation. |
| Approved snapshots | Resolver, seeder and workflow validate the exact reference-period KPI set. | The correction must address these consumers together, not only change dropdown labels. |

The user confirmed that `PMS_Trend_All.xlsx` with the existing `Inbound` / `Outbound` processing path is the operational source. `CC PMS.xlsx` was supplied for comparison, not as a replacement upload contract. Verify operational behavior against the actual cleaner/service, not the reference workbook's totals.

## Phase 1 — Establish source identity and baseline

Status: code audit, workbook identification and anonymous source-pipeline regression fixtures verified locally.

1. Confirm the file/tab used for normal processing; distinguish it from reference-only examples.
2. Record the established path: upload router → Excel processor → existing cleaner → KPI service → saved records.
3. Capture a small anonymized regression fixture from that contract: headers, units, KPI keys and labels, source values, achievements, targets, weights, final score and grade.
4. Include an over-target KPI and Inbound rows with/without UTZ so capping and fallback differences cannot be hidden by an easy fixture.

Exit gate: the expected baseline is tied to the operational source, not inferred from a month, tab-name similarity or a reference total.

## Phase 2 — Separate the upload contract from monthly overrides

Status: baseline implementation plus reviewed source-switching, tracking guards and header integration are composed locally; focused combined verification passes.

1. Use the established backend mapping as the single source for KPI identity, display label, source column and scoring behavior.
2. Remove implicit reference-template selection from the ordinary upload and new-draft paths. A date alone must not select a different KPI set, inject Productivity, override targets or change capping.
3. Keep any explicitly approved historical reference configuration immutable and identifiable; do not silently convert it to the operational contract.
4. Reuse the existing scoring implementation or a shared adapter extracted from it. Do not create a second independently maintained formula for preview/apply.
5. Store necessary contract identity in existing version/source metadata where safe; do not add a schema migration unless a demonstrated integrity requirement cannot be met otherwise.

Exit gate: without an approved monthly override, normal processing produces the established result and names for that source.

## Phase 3 — Connect target/weight editing to the same contract

Status: editor/guard completion and combined header/upload checks independently verified locally. Admin confirmation explicitly switches a legacy/reference month to original-upload settings; directions remain source-owned. Known mapped indicators may have weight zero when the total is explicitly 100%. Unknown headers do not create scored indicators.

1. Create drafts from the selected team's operational contract and exact reporting period; use stored cleaned values, not a new upload requirement.
2. Apply target and weight overrides only to that month and scope. Preserve original uploaded targets and values for audit/rollback.
3. Keep formulas, units and identity source-owned. Do not reinterpret Inbound `Other` as one fixed KPI when the existing row contract selects UTZ or Abandon.
4. Support zero-weight monitoring for mapped indicators. They remain visible when data exists, contribute zero, and do not trigger automatic redistribution of other weights.
5. A missing monitoring value is shown as unavailable, not zero. A missing required scored value identifies the KPI and affected records.
6. Handle existing drafts based on the wrong template explicitly: show the mismatch and offer an Admin-controlled replacement/revision. Never mutate saved drafts or approved versions while reading a page.
7. Preserve Admin-only authority, checksum conflict protection, approval gates, upload target-conflict rules and historical immutability.

Exit gate: save/preview/approve/apply use one source contract and one numeric interpretation. The UI does not advertise an editor whose backend contract cannot apply it.

## Phase 4 — Verify every affected path

Status: local combined regression verification complete with the unchanged baseline Marketing failure explicitly retained. No live browser/UAT or production verification is claimed. See `original-upload-review-qa-2026-10-11.md` for exact gates and source-coverage limits.

- Baseline parity: same operational row before/after refactor, including over-target values and original grade rules.
- July/August/another month: no calendar-only KPI injection; June exception preserved if part of the confirmed source contract.
- Inbound UTZ present, missing, and zero; Abandon and AHT units/directions preserved.
- Explicitly approved historical reference configuration still reads and remains immutable.
- Target-only and weight-only edits, tracking-only indicators, zero actuals, missing actuals and invalid total weights.
- Preview and committed apply produce identical results; original stored evidence and other months remain unchanged.
- Upload dry-run/commit, team dashboard, function/executive summary, roster and trends use the selected applied basis consistently.
- Rollback restores the previous result; caches cannot continue serving the prior applied version.
- Admin permissions and non-Admin denials remain intact.
- Use isolated test databases and synthetic/anonymized fixtures. No destructive tests against production.

## Phase 5 — Local handoff, then separate release approval

Status: local code review and evidence handoff complete. Release approval and production recovery remain separate and pending.

Document changed paths, tests actually run and any unresolved source differences. Preserve the earlier uncommitted frontend simplifications. No merge, push, deployment, production migration, backfill or automatic historical recalculation is included in this request. Production migration recovery remains separately controlled.

## Acceptance criteria

1. The selected operational upload, not a conversation example, determines KPI names and calculation behavior.
2. An unchanged configuration reproduces the operational baseline.
3. Changing target/weight updates the selected month without re-cleaning or re-uploading available data.
4. Tracking-only indicators remain outside the score.
5. No unknown indicator, formula, missing value or new source is silently invented.
6. Existing approved history is retained and all affected consumers are verified, not just the editor screen.

## Added source-header requirement (user clarification, 11 October)

The user supplied the actual Outbound operational header layout. It includes `AHT`, `A.AHT`, `T.AHT`, `AHT Ach%` and `T.Quality Target`; it does not include Productivity. Store an anonymized header-only fixture, not the pasted employee rows. Check source-to-backend aliases against this layout, particularly the quality target, so fallback defaults cannot hide a mismatch. Preserve existing calculations, capping and units; do not invent a KPI or add it to the score because a column appeared.

At upload, report new/unrecognized columns by their original Excel header and sheet. This is advisory, not an automatic mapping, formula change or new scored KPI. Inspect raw headers before the existing crop/normalization and deliver the warning in synchronous dry-run/commit and asynchronous job results. Surface it in the upload UI without replacing existing collision warnings or errors. The initial verified contracts are Inbound/Outbound; do not imply that unaudited team families have complete schema coverage. Wider column mapping/formula editing remains deferred. Required data errors and target-conflict rules keep their existing behavior.

## Current implementation boundary

Main source remains at `0f1e658de034ae8e90bc4298cfe685d57dd63b37`; only this plan is edited in the primary checkout. Grok 4.7/xhigh worked in separate managed worktrees. Accepted local code: guards `fd3edaf`, editor `c593d24` (composed as `9579c40`), headers `1b5a1b2` (composed as `a6181a0`). The original editor delegate's overlapping backend draft is preserved but not integrated because the stronger guard delegate is authoritative for those files. Header-author documentation is retained separately; reviewer evidence governs this plan.

Independent reviewer checks: 68 backend tests (unchanged two RED→GREEN reviewer probes plus source/period/revision suites), 132 settings tests across 12 files, type checking, lint, production build and bundle budgets passed. These are bounded editor/guard checks, not the final combined result. The full untouched local baseline has a separate existing Marketing workbook acceptance failure (131 rows vs the test's fixed 68); no assertion was changed to hide it. Grok's full-suite self-reports are retained separately and are not substituted for reviewer evidence.

All owned Grok writers have exited. The actual anonymous ExcelProcessor-to-KPIService probes were RED on untouched main and GREEN unchanged on the reviewed candidate: `T.Quality Target=0.8` is retained, Quality actual `0.4` achieves `0.5`, and a new header after Performance Grade is reported without altering the score. A direct KPIService-only caller still requires canonical column names; the alias is intentionally resolved at the upload boundary, not duplicated inside the scorer.

Independent header-only checks: 42 backend tests passed (including two unchanged reviewer probes); 132 frontend settings/upload-context tests across 15 files passed; typecheck/lint/build:ci/bundle budgets passed. Combined focused checks on `a6181a0`: 63 backend tests passed, including all four immutable reviewer regressions plus source/header/upload/job tests. Full combined frontend: 846 passed across 107 files (162.01s). Full combined backend plus the four reviewer probes: 1473 passed, one unchanged Marketing 131-vs-68 acceptance failure, one existing absent-local-dataset skip and 65 warnings (282.81s). No expectation was changed and no new skip introduced. Final combined typecheck/lint/build:ci/bundle budgets passed.

Final AST-only graph refresh: 11,277 nodes, 31,094 edges, 452 communities; known JSON/SQL extraction and community-label warnings remain. No LLM labeling or dependency installation was used. All owned writers and verification processes have exited.

### Verified header behavior and limits

- Original Outbound header-only fixture has no false warning. Case/whitespace comparison and blank/Unnamed padding do not produce extra notices.
- New headers before or after Performance Grade are reported using original sheet/header names. Notices inspect headers, not employee cell values, and are bounded to 12 notices/25 headers per notice.
- `column_warnings` remains separate from existing collision `warnings`, including dry-run/commit and asynchronous job completion. Header-looking markup renders as text in the tested UI.
- The source-proven Quality alias retains the original uploaded column. Conflicting populated target columns stop the upload before performance/KPI writes and name the columns, not employee values.
- No Productivity is injected when absent. Established optional Productivity, when actually uploaded in an ordinary month, remains monitoring-only (weight/contribution zero); explicitly approved historical reference rules remain unchanged.
- Outbound's supplied header list is authoritative for this phase. Other legacy processor sheets compare shared metadata and their configured columns; legitimate cleaner-only fields can still warn. Marketing imports are outside this header pass. This is not complete all-family mapping.
- Existing percent conversion is unchanged: ratio `0.8`, number `80` and text `80%` were verified. Ambiguous small bare percentages follow existing conversion and are not reinterpreted by this feature.

No production database, migration or source workbook was modified. Main integration, remote publication, deployment, production migration recovery and live browser/UAT verification remain separate release gates.
