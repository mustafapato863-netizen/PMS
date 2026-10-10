# Monthly evaluation runtime: final local composition

Date: 10 October 2026. Branch: `codex/evaluation-roadmap-closure`.
Composed runtime `ac11e44` and progress UI `9cf5d31`, followed by the reviewer command-hint correction below. This supersedes statements that Phase 7C2/7D are unimplemented; it is **not** a main merge, remote publication, deployment or all-team release acceptance.

## Executed final gates

| Gate | Actual result | Boundary |
|---|---|---|
| Complete backend after final correction | 1433 passed, 2 existing CI skips, 65 warnings, 256.49s | Anonymous CI-shaped environment, no exclusions or new skips. Private Marketing workbook reconciliation is still unresolved. |
| Complete frontend | 824 passed, 105 files, 195.37s | Two workers; unchanged timeouts, no automatic retries or removed cases. |
| Final frontend quality | Typecheck, full ESLint, build:ci and bundle budgets passed | Existing 512.75kB entry-chunk advisory and canvas test-environment warnings remain. |
| Independent C2 candidate composition | 149 passed, 37.57s | Before the final command-hint correction; retained separate evidence. |
| Final runtime/coordinator/bounded/public-authority regression | 93 passed, 40.46s | Includes the new owner cancel/retry presentation regression and unchanged cross-Admin audit assertions. |
| Cross-Admin recovery/atomicity/revocation | 14 passed, 27.36s | 12 real PostgreSQL16/18 cases, sequential disposable fixtures, plus 2 SQLite cases. Includes concurrent recovery, cancel versus promote, post-Team-wait committed role/activity revocation, retained identity/source and injected audit-write rollback. Not native PostgreSQL RLS certification. |
| Real login/JWT/public worker lifecycle | 1 passed, 8.21s on final code | 200 anonymous records; role matrix denial, strict request validation, disabled original owner, new active Admin capture, actual worker once, public status and latest guarded rollback. |
| Actual browser/HTTP/worker flow | Passed, 200 records | Login, approved month, keyboard Apply, queued score-neutrality, leave/reopen, confirmed cancellation, new job, real worker, 100% completion, refreshed revision history and confirmed rollback. Scores 70 → 80 → 70; original source and effective targets separately verified. No API mocks. |
| Browser layout/keyboard | 375/746/1024/1440 passed | No document horizontal overflow or page errors; actual focus and Enter activation. Follow-up checks await actual breakpoint/width transitions and desktop main/sidebar separation, not an arbitrary sleep. |
| Local 200-row worker measurement | 2.168s | Includes the worker pass and evidence query in disposable SQLite. Not production p95, RSS, linear-growth acceptance or an SLA. |
| AST graph refresh | 10982 nodes, 30255 edges, 456 communities | AST-only, no semantic/LLM refresh. Existing empty JSON/missing SQL parser warnings and relabeled community hubs retained. |

## Reviewed implementation and authority

- Evaluation worker runtime and public job routes are registered behind `PMS_EVALUATION_APPLY_JOBS_ENABLED`, default **false**. Synchronous apply remains available; capability lookup failure is not permission to fall back silently.
- Finite candidate/page budgets, keyset staging and same-worker live-lease continuation prevent an unfinished large job from endlessly restarting. Full-month source fingerprint reads on each page remain a known growth cost; drift checks were not removed for speed.
- A persisted active Admin can inspect/cancel/recover a committed job requested by another Admin. Cross-Admin management audit and mutation share a transaction; original requester and captured identity do not change. Starting, staging, promotion, heartbeat, acknowledgement and retry execution remain the original active requester's authority. Another Admin cancels unpromoted work and captures a **new** request under themselves.
- Revoked requester snapshots do not grant execution. Tests prove committed revocation before the post-Team-fence authority read; they do not claim a User-row revocation lock throughout the whole operation.
- Queue acceptance/approval does not change scores. Progress is 0 while queued, at most 99 before acknowledgement, and 100 only after success. Committed revision evidence invokes the existing consumer invalidation path, once per job/revision token; drafts and approvals do not rescore live evidence.
- Latest-only manifest rollback restores original saved evidence without reactivating old approval. A rollback marks the retained revision `rolled_back`; it does not insert an invented second apply revision.
- Outbox publication retains the existing real Redis acknowledgement requirement and durable DB cache-identity fallback. Existing separate-process summary/roster unavailable/reconnect evidence is in the cache QA report; this flow deliberately has empty Redis and does not certify every consumer's reconnect behavior.

## Defects and harness findings retained

The browser genuinely exposed stale action hints: an owner cancelled their queued job but the UI retained `can_retry=false` from its pending state. A new backend test failed with missing `can_retry`. Status and cancel/retry/recover responses now share one fresh, narrow, read-only presentation-hint query. Outcomes, command authority and audit counts are unchanged. The repeated actual browser shows Retry after cancellation and the separate regression verifies the original owner's retry response. Hints are not grants.

Earlier native reviewer expectations incorrectly required the effective SQL target to remain unchanged after an approved correction. Corrected adapters require effective target 50 **and** retained original source actual/target 40, identical KPI identities and unchanged actuals. Cancellation still requires the complete original source/target tuple. Audit-write failure is checked as the allowlisted `persistence_failed`, not a leaked injected exception. Cancel invalidates the worker token; the losing promote must return `stale_token`, while a losing cancel returns `invalid_state`. Exactly one winner, no partial score writes, one revision/outbox, preserved attribution and actual audit actor assertions remain. Original failed harnesses and XML are retained, not overwritten or reported as product defects.

PowerShell empty environment assignments removed the variable and allowed dotenv to select existing localhost Redis in an earlier invalid-isolation run. Correct anonymous runners set empty Redis **inside Python before imports**, verify the resolved settings, and restrict allowed workspaces/databases. The earlier run did touch local Redis invalidation metadata; no application database/private workbook was changed and no user Redis state was deleted or reset.

## Reproducible local evidence

Reviewer-owned files under `D:/Projects/PMS_Dashboard/tmp` include:

- `reviewer-runtime-composed-final-20261010.xml`, `reviewer-runtime-command-hints-red-20261010.xml`, `reviewer-runtime-command-hints-green-20261010.xml`.
- `reviewer-runtime-cross-admin-contract-final-20261010.xml`, immutable old native/SQLite modules and the explicitly corrected source-contract adapters.
- `reviewer-runtime-public-200-jwt-final-20261010.xml`.
- `reviewer-evaluation-runtime-browser-20261010/workflow.json`, workflow trace, settled responsive JSON and screenshots. Mobile/tablet/desktop screenshots were visually inspected; immediate-transition screenshots are not visual acceptance evidence.

These fixtures use fresh anonymous SQLite or exact disposable loopback PostgreSQL databases. User development ports 5173/8000 and production data were not used for destructive testing.

## Remaining release boundaries

Coding Employee, Submission Employee and Outbound Employee July/August 2026 remain the admitted calculation scopes. Missing approved Marketing/Pharmacy/CSR/IP Final/Managerial/Corporate references keep their editors blocked, including unproven weight-only changes. No new formula family, guessed source chronology, custom formula editor or automatic historical rescore was introduced.

Still required before release: production schema/backup/recovery rehearsal, explicit flag/operator rollout, real all-team/all-role UAT, full live-consumer/multi-process reconnect coverage and agreed production latency/query/RSS budgets. Phase 9 remains deferred. Main stays at `b2187144f3940e8680866e10b9fff25e480fce97`; no remote push or deployment is claimed.
