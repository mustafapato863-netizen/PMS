# Monthly evaluation candidate: independent verification checkpoint

Date: 9 October 2026. Final consumer integration: `ae40741750bf37f725e1815e5a5cf45775c91cf2`; reviewed consumer: `adeb33d0f64b66bffd1fcc646343e808af762621`.
This is a bounded review checkpoint, **not** complete release acceptance, production verification, or an authorization to push main.

## Independently executed gates

| Gate | Result | Evidence boundary |
|---|---|---|
| Backend full suite, CI unset | 1142 passed, 1 skipped, 1 failed; 167.80 seconds | Remaining failure is the unchanged external Marketing workbook assertion: expected 68 rows, supplied local workbook has 131. Previously reproduced on untouched main. No workbook assertion weakened or new skip added. |
| Independent focused workflow/ingestion regression | 126 passed; 9.07 seconds | Actual catalog, revision lifecycle, source goldens, upload preview/commit and resolved reads. Includes three reviewer-owned RED-to-GREEN probes for first-row aggregate fabrication and cached team deactivation. |
| Frontend full suite | 93 files, 700 tests passed; 69.42 seconds | Existing canvas test-environment warnings; no failed test. |
| Frontend typecheck and lint | Passed | Real project commands, not delegate claims. |
| Production build and bundle budgets | Passed | Existing large-chunk advisory remains; no budget bypass. |
| PostgreSQL history, correction and real upload race | 26 passed; 39.09 seconds on final integration | Exact allowlisted disposable PostgreSQL16/18 databases. Upgrade/downgrade, immutable guards, lineage and concurrent correction checks. Real seeder pin/sync holds team lock; apply waits, then refuses changed evidence as `stale_preview`, preserving uploaded score/actual/target without inserting a revision. |
| Coding UI + actual evaluation API lifecycle | Passed | Synthetic identity and in-memory DB: approved read-only; same-month revise; full 10-record impact with 8/2 pagination; approval without recalculation; explicit apply 70 to 75; confirmed rollback to original scores, targets and notes; two retained rule versions. Not full application-login coverage. |
| Outbound UI + actual evaluation API lifecycle | Passed on final integration | July-to-August copy adds Productivity10%/Attendance60%; explicit apply stores source golden79.82. Revise August target0.7/Attendance50%/Productivity20%, approve without automatic recalculation, explicitly apply79.93 under existing per-KPI caps, then rollback restores the prior complete payload/targets. July and raw/original full-precision evidence remain unchanged. September is blocked. |
| Independent authorization/history/source probes | Passed on final integration | Actual evaluation routes with persisted identities injected by synthetic middleware: non-Admin management role matrix and Manager level restrictions. Not JWT authentication. Missing/duplicate/unknown/nonfinite evidence denied; monthly NULL end-fields denied; second correction retains original workbook55 after first apply65. |
| Responsive UI and access gate | Passed | Chromium 1440/746/390px. Document and text-range bounds after wrapping long provenance/history checksums; no page errors. Manager starts no evaluation API requests; unauthenticated catalog denied. |
| Whitespace and code-graph refresh | Passed | Graph refresh is navigation evidence, not semantic calculation certification. Known JSON/SQL parser coverage warnings remain. |

Safe backend gates run with `APP_ENV=test`, `DATABASE_URL=sqlite:///:memory:`, empty `REDIS_URL`, and `CI` unset **before imports**. PostgreSQL check files are explicit opt-in (`evaluation_*_pg_checks.py`), not normal `test_*.py` discovery; fixture verifies exact loopback host, database, user and server port before disposable-schema reset. No application database or source workbook was modified.

## Reviewer corrections at this checkpoint

- Replaced the obsolete rollback-test dummy with a real SQLAlchemy session. Preserved failure/rollback/JSON assertions; strengthened error-message and empty batch/performance/KPI-table assertions. Did not change the Marketing workbook acceptance assertion.
- Added real upload/correction PostgreSQL race coverage. Cleared PostgreSQL observer statistics snapshots to avoid a false negative while checking actual lock waits.
- Wrapped long source/checksum/history strings after visual review exposed clipping that document-width assertions alone missed.
- Updated the English implementation reference and Admin guide to retain Admin-only D001, source-vs-synthetic Outbound chronology, immutable same-month D005 corrections, and explicit incomplete rollout status.
- Replaced the workflow's duplicated hardcoded audit gate and speculative period method with the shared exact-month catalog/capability contract. July-to-August reconciliation introduces the audited destination template; same-month revisions preserve selected approved custom values.
- Refresh and lock the live team before checking activity, preventing an ORM-cached active team from granting edits after deactivation.
- Multi-person reads return per-record authorized evidence rather than the first person's score/actuals as a fabricated aggregate. Explicitly corrected one old lifecycle assertion to require both actual saved scores; no assertion skip or tolerance widening.
- Approved upload pins retain full-precision raw inputs before replacing applied targets; rich DTOs survive preview, commit and resolved reads. Missing Productivity cannot fall back to Available Time or rounded SQL decoys. Mixed legacy/pinned records stay mixed, without current-approval overlays.
- The initial extended browser expected arithmetic omitted the existing employee per-KPI cap. Verified the engine contract and corrected the independent expected calculation; application scoring was not changed to fit a test.

## CI and local merge checkpoint

Earlier isolated PR31/32 CI was not green: PR31's older-base Outbound fixtures violated the exact-month CHECK; PR32's obsolete Marketing rollback dummy lacked a real connection. Both are corrected in the final integration and pass the local regression suite. A fresh isolated final-review CI run is required; old failed runs are not presented as acceptance.

Consumer source review, original full-precision upload goldens, mixed-basis guards and final PostgreSQL/browser checks above have passed. Final review PR34 run37928384449 passed backend, frontend and containers on `bb86ee766b248631270ef0c1c82da1396dcb5048`. Earlier integrated run37927968812 also passed and reported1142 backend tests passed/2 existing CI skips; the external workbook test retains its original CI skip policy. Subsequent commits change documentation only, verified by path diff. This closes the isolated CI gate for the supported local integration, not the unresolved external local Marketing workbook baseline or wider release gates.

## Wider rollout boundaries

- Unsupported formula/period/level/position scopes remain blocked. A populated catalog is not all-team activation.
- Complete application-login browser coverage, full downstream all-team/UAT matrix, measured large-scope performance and production-schema/recovery validation remain separate gates.
- Source July/August Outbound attendance target is65% in both months.55-to65 is synthetic correction evidence, not source chronology.

This checkpoint was committed before the authorized local main merge. No main/GitLab push or production deployment is authorized by this review. Remote main auto-deploys, so release publication remains separate from reviewed local integration.
