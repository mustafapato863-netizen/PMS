# Monthly evaluation: preserve the operational upload contract

Date: 11 October 2026
Status: source audit completed; user confirmed the operational workbook and requested Grok implementation. Dispatch is blocked by Grok CLI authentication, not by a missing product decision.

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

Status: code audit and workbook identification complete; regression fixture verification remains part of implementation.

1. Confirm the file/tab used for normal processing; distinguish it from reference-only examples.
2. Record the established path: upload router → Excel processor → existing cleaner → KPI service → saved records.
3. Capture a small anonymized regression fixture from that contract: headers, units, KPI keys and labels, source values, achievements, targets, weights, final score and grade.
4. Include an over-target KPI and Inbound rows with/without UTZ so capping and fallback differences cannot be hidden by an easy fixture.

Exit gate: the expected baseline is tied to the operational source, not inferred from a month, tab-name similarity or a reference total.

## Phase 2 — Separate the upload contract from monthly overrides

Status: ready for delegated implementation after Grok authentication.

1. Use the established backend mapping as the single source for KPI identity, display label, source column and scoring behavior.
2. Remove implicit reference-template selection from the ordinary upload and new-draft paths. A date alone must not select a different KPI set, inject Productivity, override targets or change capping.
3. Keep any explicitly approved historical reference configuration immutable and identifiable; do not silently convert it to the operational contract.
4. Reuse the existing scoring implementation or a shared adapter extracted from it. Do not create a second independently maintained formula for preview/apply.
5. Store necessary contract identity in existing version/source metadata where safe; do not add a schema migration unless a demonstrated integrity requirement cannot be met otherwise.

Exit gate: without an approved monthly override, normal processing produces the established result and names for that source.

## Phase 3 — Connect target/weight editing to the same contract

Status: pending.

1. Create drafts from the selected team's operational contract and exact reporting period; use stored cleaned values, not a new upload requirement.
2. Apply target and weight overrides only to that month and scope. Preserve original uploaded targets and values for audit/rollback.
3. Keep formulas, units and identity source-owned. Do not reinterpret Inbound `Other` as one fixed KPI when the existing row contract selects UTZ or Abandon.
4. Support zero-weight monitoring for mapped indicators. They remain visible when data exists, contribute zero, and do not trigger automatic redistribution of other weights.
5. A missing monitoring value is shown as unavailable, not zero. A missing required scored value identifies the KPI and affected records.
6. Handle existing drafts based on the wrong template explicitly: show the mismatch and offer an Admin-controlled replacement/revision. Never mutate saved drafts or approved versions while reading a page.
7. Preserve Admin-only authority, checksum conflict protection, approval gates, upload target-conflict rules and historical immutability.

Exit gate: save/preview/approve/apply use one source contract and one numeric interpretation. The UI does not advertise an editor whose backend contract cannot apply it.

## Phase 4 — Verify every affected path

Status: pending.

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

Status: pending.

Document changed paths, tests actually run and any unresolved source differences. Preserve the earlier uncommitted frontend simplifications. No merge, push, deployment, production migration, backfill or automatic historical recalculation is included in this request. Production migration recovery remains separately controlled.

## Acceptance criteria

1. The selected operational upload, not a conversation example, determines KPI names and calculation behavior.
2. An unchanged configuration reproduces the operational baseline.
3. Changing target/weight updates the selected month without re-cleaning or re-uploading available data.
4. Tracking-only indicators remain outside the score.
5. No unknown indicator, formula, missing value or new source is silently invented.
6. Existing approved history is retained and all affected consumers are verified, not just the editor screen.

## Current implementation boundary

No scoring or upload code has been changed under this plan. The existing frontend changes from the preceding task remain in place. Grok 1.0.41 is installed, but its model-list preflight reports `You are not authenticated`; no implementation process was dispatched. The prepared implementation brief is `tmp/grok-original-upload-source-20261011-brief.txt` in the primary workspace. After login, use an isolated managed worktree based on the verified primary HEAD and review/test its result before integrating anything.
