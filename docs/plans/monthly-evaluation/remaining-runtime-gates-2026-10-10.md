# Remaining runtime integration gates

## Superseding local checkpoint

Canonical summary/roster Redis-unavailable separate-process cache gate now passes on owned PostgreSQL16/18 after a two-line pinned-summary key-shadow repair, with repeated post-apply and post-rollback hits. Focused anonymous CI53PASS; native2PASS13.61s. Follow-up actual owned Redis7 pause/socket-timeout/unpause reconnect, realINCR/PUBLISH/subscriber/ACK and latest rollback also pass2native18.13s. Container stopped/auto-removed; no production connection. See `docs/qa/evaluation-cross-process-cache-2026-10-10.md`. These close the bounded canonical unavailable/reconnect gates only; all-consumer/runtime certification remains open.

Queue/publisher source checkpoint `81d3b03` is now locally accepted after complete source/test review and independent gates: full backend1400PASS with only unchanged MarketingFAIL/existingSKIP, sequential owned PostgreSQL100PASS, explicit anonymous CI-shaped115PASS. See `docs/qa/evaluation-queue-outbox-composition-2026-10-10.md`. Legacy queue isolation is enforced; dormant default-disabled outbox delivery is implemented but not registered or activated. Separate Phase7C1 lease coordinator candidate is in progress, not accepted. No main/production change.

Public and bounded authority repairs are locally composed at `dbecea2` after independent review. The complete composed backend gate is1329PASS plus the unchanged Marketing131vs68FAIL/existingSKIP; composed native gates18PASS, real JWT/public manifest API scenario1PASS. See `docs/qa/evaluation-bounded-authority-composition-2026-10-10.md` for actual evidence and limits. The historical unauthorized-success failures below are retained as RED evidence and are no longer current candidate outcomes. Nonlocking post-fence authority is not transaction-wide revocation serialization.

Dormant bounded staging/promotion/manifest adapters are implemented, with correctness and bounded-retention gates recorded, but repeated full-source scans remain a measured growth-cost limit. User actual largest cohort200/page100 measured1.516s with tracing in synthetic SQLite; later owned PostgreSQL runs favor page200 latency at higher traced memory, but do not establish a p95 or production budget. Default remains100. Neither worker runtime nor publisher/UI is activated. Legacy queue isolation and dormant outbox delivery are accepted as described above; Phase7C1 coordinator alone remains an isolated unaccepted candidate. Main/publish/release authority remains separate.

Date:10October2026. Source audit of accepted closure `856cf4d`. This is a dependency checklist, not evidence that these features exist, and not permission to publish. Phase7B must independently pass before Phase7C implementation is accepted.

## 7B acceptance first

Retain the independent stage-query budget, complete manifest parent/pair binding and native capture/stage overlap regressions. A self-reported green suite is insufficient. Promotion must remain one transaction with fault-injected score/revision/outbox rollback. Preserve all admission, fresh Admin, exact-month, engine/source/rules, epoch and lineage checks. Measure keyset/session retention and full-cohort work, not just one bounded page's memory.

The10October resumed review reproduced committed Admin revocation while an operation waited for the Team fence. Independent bounded stage/promote probes failed4native cases; independent public Apply/Rollback probes failed8native cases (role revocation or deactivation on PostgreSQL16/18). These historical RED results were genuine unauthorized-success outcomes, not setup errors. Separate repairs were subsequently reviewed, rerun and locally composed in the superseding checkpoint. Preserve the persisted authority recheck after acquiring the fence; entry-only or snapshot-only checks are insufficient. Do not claim stronger revocation serialization than the tests prove.

The current bounded candidate retains whole-month fingerprint reads before every staged page. This is a known cost, not an accepted linear-time performance result. Measure source-row visits, total SQL, retained objects and traced memory at increasing cohort sizes. A proposed source-generation optimization would be a separate schema/transaction design requiring complete mutation coverage and migration/concurrency verification; none has been implemented or approved. Do not simply skip whole-cohort drift checks or substitute TTL freshness.

## 7C worker and recovery

Current public job kinds and `worker.process_job_once` support only upload and two report kinds. Accepted queue isolation filters current persisted legacy kind for claim, heartbeat, progress, success, failure and expired-lease requeue; generic status/worker reads reload identity. These paths do not coordinate evaluation-control epochs and deliberately reject evaluation work. Adding a dispatch branch alone is unsafe.

- Keep evaluation runtime disabled by default until explicitly enabled. Disabled workers must not claim evaluation jobs. Existing upload/report gates must continue to pass unchanged.
- Define enqueue, claim and retry transactions across job and evaluation control using the accepted lock hierarchy, including the existing outer team fence. Never expose roster payloads in job request/result; preserve the2048-character foundation cap.

The accepted generic `claim_next` now filters the three legacy kinds before `FOR UPDATE SKIP LOCKED`; actual PostgreSQL isolation and committed stale-kind probes passed. Public creation still rejects evaluation_apply. The dormant bounded service's `capture` currently transitions both control/job to staging/running in its own transaction, without a worker lease. Do not reuse that as a queue-acceptance wrapper: explicitly separate pending enqueue from lease-fenced start, preserving captured proof, ownership and immutable identity. A successful enqueue is not a completed apply.
- Reclaim increments/fences the active epoch before any old worker can stage or promote. Heartbeats and committed progress require matching worker, live lease and epoch. Preserve immutable prior-attempt stage evidence.
- Cancellation before promotion must leave no scored partial writes. Promotion versus cancellation/retry/revocation must serialize; successful commit must not be reported as cancelled afterward. Fresh persisted active Admin authorization is required, not the actor snapshot.
- Crash/retry must handle committed promotion with missing job-success acknowledgement as an idempotent outcome, not duplicate history or a false failure. Retain latest-only rollback and no old approval reactivation.
- Add actual authenticated Admin-only status/cancel/retry tests and real two-worker PostgreSQL overlap/recovery gates on the owned disposable pair. Do not run destructive production tests.

## Cache and consumers

`evaluation_cache_identity` already adds committed configuration/revision/upload identity to the shared dashboard cache. Do not replace this with Redis alone. A reviewed dormant publisher now implements at-least-once delivery, acknowledges only after actual direct commands and DB commit, retains failed deliveries and tolerates a crash between Redis increment and acknowledgment. It is default-disabled and unregistered. Canonical summary/roster separate-process unavailable/reconnect gates now pass as documented above; all-consumer/runtime integration remains open, and injected-client native tests alone are not that certification.

Audit actual reader ownership before changing caches. Current Insights workspace route regenerates through `InsightsService`; its request-local comparison caches are not a demonstrated shared stale-cache defect. Current Story context caches are request-local. Reports use shared data-version metadata, and regenerated versus saved outputs must remain distinct.

Test another process with a warm cache while Redis is unavailable/reconnects, including apply and rollback. All live summaries, drivers, roster/profile, Insights, planning-derived evidence and regenerated reports must observe the committed basis. Human plans/actions, manually entered targets and previously saved report bytes must not be rewritten.

## 7D settings UI

The existing committed-evidence invalidation covers performance, executive summary, report center, Insights, team configurations, weights and BSC; draft/revise/approve invalidates settings only. Async completion must invoke the same committed path, not treat queue acceptance or approval as score changes.

Provide bounded progress, safe failure/retry/cancel states, leave-navigation/reopen recovery and revision links. Only successful committed apply/rollback refreshes live evidence. Prove keyboard/mobile/tablet behavior and stale responses with real JWT/API-driven browser checks; no optimistic all-roster score mutation.

## Release remains separate

Measure query/RSS/latency against increasing padded cohorts and state what was actually measured; no invented p95 SLA or universal speedup. Missing approved family sources still block admission. The unchanged Marketing131-versus68 fixture failure remains an explicit full-suite exception to resolve without weakening assertions. Production migration/recovery, all-role/all-team UAT, main publication and deployment verification are separate gates.
