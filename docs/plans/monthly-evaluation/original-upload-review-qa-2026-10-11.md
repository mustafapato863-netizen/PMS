# Original-upload monthly settings and header notices — reviewer QA

Date: 11 October 2026
Status: reviewed local candidate; independent combined verification complete with one unchanged baseline Marketing acceptance failure. Not an all-green release or release authorization.

## Scope and implementation ownership

The operational Inbound/Outbound upload path remains authoritative for mapped KPI identities, labels, units, directions and formulas. Monthly settings change explicit targets and weights, not the source schema. The reference workbook supplied during design is not a replacement operational contract.

Grok 4.7/xhigh implemented three isolated streams. Codex read their code and tests, reran the gates independently after each writer exited, and composed only accepted code on `codex/original-upload-review`:

- Base/main: `0f1e658de034ae8e90bc4298cfe685d57dd63b37`.
- Backend tracking/source-switch guards: `fd3edaf`.
- Frontend original-source confirmation: author `c593d24`, composed `9579c40`.
- Upload header notices/quality alias: author `1b5a1b2`, composed `a6181a0`.

The first editor author's overlapping backend draft was not composed; the independently verified guard stream supersedes it. Author drafts and reports remain available in their isolated worktrees. No remote PR, main source merge, push, deployment, production migration, production backfill or private workbook edit was performed.

## Verified behavior

### Monthly editor and guards

An Admin can explicitly switch a reference draft to original-upload settings with confirmation and an expected checksum. A stale Admin cannot overwrite a newer draft. Disabled/non-Admin actors are denied before mutation. Existing operational versions are idempotent, and open apply jobs or conflicting drafts prevent unsafe switching. Approved source snapshots and revision lineage are preserved.

Directions remain source-owned; the Inbound Other line explains its row-dependent UTZ/Abandon choice. Monthly drafts are isolated by scope, performance level and period. Entering a changed numeric target selects a fixed target rather than silently retaining workbook mode. Known mapped indicators may be tracking-only with weight zero; the explicit scored weights must total 100%, without automatic redistribution. Missing required actuals remain errors, not fabricated zeros.

### Upload headers

The user's original Outbound header list was copied without private employee rows. It contains AHT and `T.Quality Target`, but no Productivity. Raw headers are inspected in memory before normalization/cropping, including columns after Performance Grade. Original sheet/header spelling is preserved in a dedicated `column_warnings` field, separate from existing collision warnings.

Extra unmapped columns are advisory and do not create scoring rules or change totals. The original fixture produces no false warning, and tested whitespace/case variants and blank/Unnamed padding do not warn. Notices are bounded to 12 groups and 25 headers per group. They contain header names, not employee cells. Sync success/error and async completion render names as text; markup-looking headers do not become HTML.

The actual ExcelProcessor-to-KPIService path previously replaced `T.Quality Target=0.8` with the canonical default `0.95`. The source-proven upload alias now preserves the original column and produces Quality achievement `0.5` from actual `0.4`. Equivalent `0.8`, `80` and `80%` spellings are verified under the existing percent conversion. Conflicting populated canonical/alias columns stop the upload before performance/KPI writes and identify the columns, not employee values.

Absent Productivity is not injected. Established optional Productivity, when actually supplied for an ordinary month, remains tracking-only with zero weight/contribution; explicitly approved historical reference behavior is preserved.

## Independent verification evidence

All backend checks used the reviewer runner that sets test SQLite, present-empty Redis and disabled automatic seeding before application imports. Fixtures are anonymous; production was not tested or changed.

| Check | Actual reviewer result |
| --- | --- |
| Header candidate: real pipeline probes + header/upload/collision/productivity/job suites | 42 passed, 4.62 seconds |
| Header UI candidate: settings + background upload context | 132 passed / 15 files, 18.19 seconds |
| Combined candidate: four unchanged reviewer probes + source/header/upload/job suites | 63 passed, 7.79 seconds |
| Combined full frontend | 846 passed / 107 files, 162.01 seconds |
| Combined TypeScript, lint, production build and bundle budgets | Passed |
| Combined full backend plus four immutable reviewer probes | 1,473 passed / 1 unchanged Marketing acceptance failure / 1 existing local-dataset skip / 65 warnings, 282.81 seconds |
| Final AST graph refresh | 11,277 nodes / 31,094 edges / 452 communities |

The four unchanged reviewer regressions were genuinely RED on untouched main: tracking-only mapped keys rejected, stale checksum ignored, original Quality target ignored, and a new post-grade header not reported. All four are GREEN unchanged on the combined candidate. No old assertions were weakened or new skips added to make these checks pass.

The combined full run repeated exactly the unchanged Marketing failure: `test_real_marketing_workbook_imports_with_incomplete_rows_excluded` imports 131 rows versus a fixed expectation of 68. The untouched baseline already failed this assertion. The only existing skip is scoring characterization requiring the local ignored dataset. CI was not forced to bypass the Marketing check, and no new skip or weakened expectation was introduced. This remains a release-test data/expectation issue, not an all-green claim; it must not be hidden by changing the assertion without source evidence.

## Remaining limits and release gates

- The supplied Outbound header catalog is verified. Other legacy processor sheets recognize shared metadata and configured columns only, so legitimate cleaner-only columns can still warn. Marketing imports are outside this header pass. This is not complete all-family source mapping.
- Calling the internal KPIService directly with only an alias bypasses the upload adapter; internal callers still require canonical keys. The real upload path, rather than this bypass, is the acceptance boundary.
- Existing percent conversion for ambiguous small bare numbers was not redesigned. No new formula editor, arbitrary KPI mapping or inferred raw-data repair is introduced.
- Actual browser/E2E/UAT was not run for this new candidate. UI workflows were tested in jsdom; this does not prove every responsive layout.
- Vite's existing large-chunk advisory and jsdom canvas warnings remain non-fatal. Bundle budgets pass. No dependency was installed to hide a warning.
- AST refresh has known zero-node JSON/config and missing SQL-parser coverage warnings, plus community relabeling notices. No LLM labeling or dependency installation was performed; the graph is navigation evidence, not numerical proof.
- Missing approved goldens for other scoring families remain blocked. No all-team calculation coverage or production schema readiness is claimed.
- Production migration recovery, async infrastructure readiness, deployment and live acceptance need separate release approval. Production's failed migration was not retried.

The primary checkout retains only its reviewer-plan edit; source code is on the local review branch. All owned Grok writers and verification processes have exited. At handoff usage was 89% five-hour / 30% weekly used, below the user's 98% stop floor; no reset credit was consumed.
