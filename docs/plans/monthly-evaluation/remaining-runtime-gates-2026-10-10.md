# Remaining runtime integration gates

Date:10October2026. Source audit of accepted closure `856cf4d`. This is a dependency checklist, not evidence that these features exist, and not permission to publish. Phase7B must independently pass before Phase7C implementation is accepted.

## 7B acceptance first

Retain the independent stage-query budget, complete manifest parent/pair binding and native capture/stage overlap regressions. A self-reported green suite is insufficient. Promotion must remain one transaction with fault-injected score/revision/outbox rollback. Preserve all admission, fresh Admin, exact-month, engine/source/rules, epoch and lineage checks. Measure keyset/session retention and full-cohort work, not just one bounded page's memory.

## 7C worker and recovery

Current public job kinds and `worker.process_job_once` support only upload and two report kinds. `claim_next`, heartbeat, progress, success, failure and expired-lease requeue currently use legacy job ownership without evaluation-control epoch coordination. Adding a dispatch branch alone is unsafe.

- Keep evaluation runtime disabled by default until explicitly enabled. Disabled workers must not claim evaluation jobs. Existing upload/report gates must continue to pass unchanged.
- Define enqueue, claim and retry transactions across job and evaluation control using the accepted lock hierarchy, including the existing outer team fence. Never expose roster payloads in job request/result; preserve the2048-character foundation cap.
- Reclaim increments/fences the active epoch before any old worker can stage or promote. Heartbeats and committed progress require matching worker, live lease and epoch. Preserve immutable prior-attempt stage evidence.
- Cancellation before promotion must leave no scored partial writes. Promotion versus cancellation/retry/revocation must serialize; successful commit must not be reported as cancelled afterward. Fresh persisted active Admin authorization is required, not the actor snapshot.
- Crash/retry must handle committed promotion with missing job-success acknowledgement as an idempotent outcome, not duplicate history or a false failure. Retain latest-only rollback and no old approval reactivation.
- Add actual authenticated Admin-only status/cancel/retry tests and real two-worker PostgreSQL overlap/recovery gates on the owned disposable pair. Do not run destructive production tests.

## Cache and consumers

`evaluation_cache_identity` already adds committed configuration/revision/upload identity to the shared dashboard cache. Do not replace this with Redis alone. The outbox has no publisher yet: publish at least once, acknowledge only after actual success, retain failed deliveries and tolerate a crash between Redis increment and acknowledgement.

Audit actual reader ownership before changing caches. Current Insights workspace route regenerates through `InsightsService`; its request-local comparison caches are not a demonstrated shared stale-cache defect. Current Story context caches are request-local. Reports use shared data-version metadata, and regenerated versus saved outputs must remain distinct.

Test another process with a warm cache while Redis is unavailable/reconnects, including apply and rollback. All live summaries, drivers, roster/profile, Insights, planning-derived evidence and regenerated reports must observe the committed basis. Human plans/actions, manually entered targets and previously saved report bytes must not be rewritten.

## 7D settings UI

The existing committed-evidence invalidation covers performance, executive summary, report center, Insights, team configurations, weights and BSC; draft/revise/approve invalidates settings only. Async completion must invoke the same committed path, not treat queue acceptance or approval as score changes.

Provide bounded progress, safe failure/retry/cancel states, leave-navigation/reopen recovery and revision links. Only successful committed apply/rollback refreshes live evidence. Prove keyboard/mobile/tablet behavior and stale responses with real JWT/API-driven browser checks; no optimistic all-roster score mutation.

## Release remains separate

Measure query/RSS/latency against increasing padded cohorts and state what was actually measured; no invented p95 SLA or universal speedup. Missing approved family sources still block admission. The unchanged Marketing131-versus68 fixture failure remains an explicit full-suite exception to resolve without weakening assertions. Production migration/recovery, all-role/all-team UAT, main publication and deployment verification are separate gates.
