# Phase 7A independent review: rejected candidate checkpoint

Date: 10 October 2026 (review commands ran late 9 October UTC). Candidate: isolated `codex/evaluation-durable-apply-foundation`, based on `625abf4`. This document records independently observed failures, not acceptance of the candidate or deployment of the migration. Main, application databases and private workbooks were not changed.

## Source review and boundaries

The reviewer read the model diff, complete foundation helper, migration, SQLite tests, opt-in PostgreSQL module and contract. The first Grok session completed successfully, reporting 14 SQLite tests and a 40-case focused suite. The reviewer independently ran the 14 SQLite cases: they passed. Public job kinds, worker dispatch, evaluation scoring, synchronous apply/rollback, frontend and ordinary authorization remained outside this foundation slice.

The proposed tables alone do not implement bounded processing, progress, cancellation, retry, atomic promotion or outbox delivery. They do not establish production memory, query or latency budgets. Unknown-family calculation editors remain blocked on unavailable approved source references.

## PostgreSQL test setup: failures and corrections

Only the pre-existing disposable allowlist was used, sequentially: loopback ports 55432/55433, databases `pms_eval_review_fix16`/`pms_eval_review_fix18`, user `pms_eval_test`. The module requires `APP_ENV=test`, bootstrap `DATABASE_URL=sqlite:///:memory:`, empty Redis URL and an allowed public search path before importing application code. No production or user development database was reset.

1. Original foundation fixture reset public, then attempted the entire migration chain from an empty schema. All eight PostgreSQL cases errored because the historical root migration alters existing tables (`employees` was absent). This did not prove a defect in the new migration.
2. The reviewer changed the fixture to a representative predecessor rather than pretending the root was a bootstrap. An initial reviewer edit omitted the prior-kind constant import; that NameError was corrected.
3. A first representative job table created by ORM metadata lacked migration server defaults. The result was two passes and six failures, including missing job status defaults. This was a test-fixture mismatch, not a reason to alter the existing production model defaults.
4. The final predecessor fixture creates non-job/non-foundation parent tables, runs the unchanged actual prior processing-job migration under Alembic Operations, stamps `f7c3a9e1d5b8`, then upgrades the new foundation migration. This verifies the new predecessor-to-head step, NOT an empty-database full-chain bootstrap.

With that corrected fixture, the eight-case PostgreSQL gate returned **four passes and four failures /16.95 seconds**. Actual direct-SQL constraints and empty downgrade passed on both engines. The upgraded-schema and populated-downgrade assertions failed because the verifier reported twenty expression drifts against PostgreSQL's native casts, parentheses and `ANY` deparsing. Populated downgrade itself correctly refused before DDL; its subsequent verifier assertion failed. Do not remove the verifier assertion or accept constraints by name alone to turn this green.

## Independently reproduced concurrency defect

The reviewer added an opt-in two-connection regression for each engine and each mutation:

- changing `processing_jobs.claim_epoch`;
- changing the staged performance record's month.

The test pauses a stage INSERT **after** the real BEFORE guard has validated it, using a separate test-only trigger and advisory lock. A second connection tries the conflicting update with a bounded lock timeout. It must not commit ahead of the validated stage write. Cleanup releases the pause and joins the writer even if an assertion fails.

Current candidate result: **four failures /9.71 seconds**. Each conflicting update committed while the validated old stage writer was paused. The guard reads control, job and record metadata without a serialization lock. Sequential rejection of an already-stale epoch is insufficient evidence for this overlapping race.

The regression is in `Backend/tests/evaluation_apply_foundation_pg_checks.py`; it remains outside normal test collection and does not authorize broader databases. The candidate is not accepted for integration. A fix must preserve consistent lock ordering and immutable old-epoch lineage, not merely add a check after the stale write or weaken the regression.

## Rework and next gate

The same Grok session was resumed with a bounded review brief, model `grok-4.7`, effort `xhigh`, 45 turns and a 25-minute watchdog. It may modify only the isolated foundation slice and run anonymous SQLite gates; PostgreSQL connections/reset remain forbidden to the delegate. The reviewer will inspect its entire resulting diff and independently rerun the allowlisted engines after the process stops.

Requested corrections include semantic expression verification, actual attached/enabled trigger verification, referenced composite foreign-key columns, essential index predicates/keys, the overlapping race and portable UUID mapping already proven in the closure branch. These are requests, not completed results.

Artifacts: `D:/Projects/PMS_Dashboard/tmp/grok-evaluation-durable-foundation-20261010` and `D:/Projects/PMS_Dashboard/tmp/grok-evaluation-durable-foundation-review-20261010`. The queued Phase7B brief is explicitly marked `NOT-DISPATCHED`; schema acceptance must precede stager/promotion work.

No full backend acceptance, production recovery, native RLS certification, all-team activation, merge into main, push or deployment is claimed here. The known independent Marketing import fixture failure (131 source rows versus 68 expected) remains separate and unresolved.
