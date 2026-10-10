# PMS-EVAL-001 composed foundation and consumers verification

Date: 10 October 2026. Reviewed local code: `a56d59e`, composing `6a90e819084c27f7b60934022adefb1908c77e80` and the accepted consumer slice `c5ee689f0cd40815cedf547d3dc1b1d8f4ab6602`. No main publication or deployment.

## Independent gates

| Gate | Observed result |
|---|---|
| Full normal backend | 1268 passed, one unchanged Marketing failure (131 vs68 expected), one existing skip,63warnings;235.84s. Not a green full suite. |
| Full frontend | 775 passed,103files;169.28s. Two workers, unchanged test timeouts; no new retries/exclusions. |
| Native PostgreSQL16/18 | 72 passed;167.22s. Five opt-in modules: history, monthly revisions, upload races, apply foundation and independent catalog tamper. |
| Frontend lint/typecheck/build | Passed; build:ci bundle budgets passed. Existing large-chunk/canvas warnings remain. |
| AST-only graph | 10114nodes,27466edges,438communities. Existing JSON/SQL parser and label warnings; no semantic API refresh. |
| Actual JWT/API and browser | Passed again on the composed workspace; six routes, four widths (24checks), no page errors or document/note overflow. |

Backend and PostgreSQL logs are retained in primary workspace `tmp/reviewer-closure-consumers-full-backend-20261010.log` and `tmp/reviewer-closure-consumers-72pg-20261010.log`. Other independent gate terminal outputs were inspected to completion.

## Actual browser proof

Owned backend started05:09UTC from the exact composed closure workspace; fixture `tmp/reviewer-basis-fixture-20261010.json` records that workspace, anonymous scratch database and backendPID35248. Owned closure Vite started05:10UTC on5319. Final proof was written05:11:01UTC: `tmp/reviewer-basis-browser-evidence-20261010/proof.json`, 24route/viewport entries, zero page errors, current basis `changed`, membership `stable`, raw performance `partial`, reasons `kpi_set` and `weight`. This deliberately does not claim full raw equivalence.

Routes: `/executive`, `/departmental-summary`, `/function-summary/call-center`, `/insights`, `/planning`, and the actual newly created report editor. All at375/746/1024/1440 pixels with August2026 scope. Report draft `444b54c0-0add-4e05-b2c6-9ddf620104a6` identifies this run; proof does not contain a workspace field, so the matching fixture and run-specific draft corroborate provenance.

- Every approval preserved all persisted PerformanceRecord/KPIValue columns; approval is not rescoring.
- Explicit apply produced approved July82.85/August79.82 goldens, July four KPIs and August five including Productivity; original source preserved.
- Fresh actual Performance Team and Function Director JWTs were denied monthly management (403), not merely hidden by UI.
- Actual Planning POST/detail GET carried linked basis annotation; human60/80/70/Draft summary was unchanged after navigation.
- Actual Story template/draft/page APIs carried the79.82/82.85 movement and basis note; report definition unchanged after navigation.
- No read or UI navigation changed scored records. Screenshots retained for375/746.

Only validated backend35248 and closure Vite35984 were stopped after exact command and listener ownership checks. Scratch SQLite and evidence remain; user5173/8000 and private databases were not changed. Native PostgreSQL tests reset only owned loopback55432/55433 allowlisted databases.

## Not certified

The existing Marketing workbook expectation remains unresolved; no bypass or changed expected value. Missing family/level goldens keep unsupported configuration edits blocked. Phase7B bounded runtime, worker dispatch, progress/cancel/retry, production recovery, all-role UAT and deployment are not certified by these gates. Saved generated report bytes remain governed by the existing immutable-snapshot tests; this browser test checks the live draft definition, not every saved artifact format.
