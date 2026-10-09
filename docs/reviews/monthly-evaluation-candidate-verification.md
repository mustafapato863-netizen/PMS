# Monthly evaluation candidate: independent verification checkpoint

Date: 9 October 2026. Integration base: `747ffba4ff97e6a9a388fcc2a2281a108f50d19c`.
This is a bounded review checkpoint, **not** complete release acceptance, production verification, or an authorization to push main.

## Independently executed gates

| Gate | Result | Evidence boundary |
|---|---|---|
| Backend full suite, CI unset | 1132 passed, 1 skipped, 1 failed; 175.73 seconds | Remaining failure is the unchanged external Marketing workbook assertion: expected 68 rows, supplied local workbook has 131. Previously reproduced on untouched main. No assertion weakened or new skip added. |
| Frontend full suite | 93 files, 700 tests passed; 69.42 seconds | Existing canvas test-environment warnings; no failed test. |
| Frontend typecheck and lint | Passed | Real project commands, not delegate claims. |
| Production build and bundle budgets | Passed | Existing large-chunk advisory remains; no budget bypass. |
| PostgreSQL history and correction suites | 24 passed | Explicit allowlisted disposable databases on PostgreSQL 16 and 18. Upgrade/downgrade, immutable guards, lineage and correction concurrency checks. |
| Real upload-versus-correction race | 2 passed; final run 6.72 seconds | Real seeder pin/sync holds team lock on both PostgreSQL versions. Apply waits, then rejects changed evidence as `stale_preview`. Uploaded score/target/actual remain intact; no revision is inserted. |
| Coding UI + actual evaluation API lifecycle | Passed | Synthetic identity and in-memory DB: approved read-only; same-month revise; full 10-record impact with 8/2 pagination; approval without recalculation; explicit apply 70 to 75; confirmed rollback to original scores, targets and notes; two retained rule versions. Not full application-login coverage. |
| Responsive UI and access gate | Passed | Chromium 1440/746/390px. Document and text-range bounds after wrapping long provenance/history checksums; no page errors. Manager starts no evaluation API requests; unauthenticated catalog denied. |
| Whitespace and code-graph refresh | Passed | Graph refresh is navigation evidence, not semantic calculation certification. Known JSON/SQL parser coverage warnings remain. |

Safe backend gates run with `APP_ENV=test`, `DATABASE_URL=sqlite:///:memory:`, empty `REDIS_URL`, and `CI` unset **before imports**. PostgreSQL check files are explicit opt-in (`evaluation_*_pg_checks.py`), not normal `test_*.py` discovery; fixture verifies exact loopback host, database, user and server port before disposable-schema reset. No application database or source workbook was modified.

## Reviewer corrections at this checkpoint

- Replaced the obsolete rollback-test dummy with a real SQLAlchemy session. Preserved failure/rollback/JSON assertions; strengthened error-message and empty batch/performance/KPI-table assertions. Did not change the Marketing workbook acceptance assertion.
- Added real upload/correction PostgreSQL race coverage. Cleared PostgreSQL observer statistics snapshots to avoid a false negative while checking actual lock waits.
- Wrapped long source/checksum/history strings after visual review exposed clipping that document-width assertions alone missed.
- Updated the English implementation reference and Admin guide to retain Admin-only D001, source-vs-synthetic Outbound chronology, immutable same-month D005 corrections, and explicit incomplete rollout status.

## Required before local main merge

- Independently review the active workflow-consumer lane, including exact-month catalog calls, July-to-August reconciliation, same-month custom-value preservation and shared capability guards.
- Prove original full-precision Outbound Productivity/other source inputs survive actual approved upload preview, commit, correction, resolved reads and successive revisions.
- Verify mixed authorized legacy/pinned evidence is described truthfully and no current approval overlays old records.
- Repeat affected regression, PostgreSQL and browser gates on the accepted final integration. Reconcile the external Marketing workbook baseline separately; never hide it.
- Keep unsupported formula/period/level/position scopes blocked. A populated catalog does not imply all-team activation.

No main merge, main/GitLab push or production deployment has occurred at this checkpoint. Remote main auto-deploys, so release publication remains a separate action after the reviewed local integration.
