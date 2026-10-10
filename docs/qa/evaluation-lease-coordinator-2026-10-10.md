# Dormant evaluation lease coordinator

Implementer record for a default-disabled persisted lease coordinator. This note is advisory. It is not independent acceptance, a completed Phase 7C, a release, or evidence from PostgreSQL, the full backend suite, a browser, or a performance run.

Date: 2026-10-10. Checkout: `C:\Users\sghd70204\.codex\worktrees\evaluation-lease-coordinator\PMS_Dashboard`, HEAD `81d3b038ed6b0932ef6ba4c313c80d4a5d26b0e7`. No commit, push, pull request, or deploy. No private workbook, user database, server, Redis, container, or PostgreSQL process was started. The opt-in native file was not executed. Marketing's existing 131-versus-68 failure was not edited and was not re-run.

`graphify-out/graph.json` was absent before these edits, so there was no graph query. After the code existed, `graphify update .` ran as AST extraction only. The result is in the checks section below.

## Files

- `Backend/services/evaluation/bounded_apply.py` — two caller-owned seams. Defaults preserve the public capture and promote behavior.
- `Backend/services/evaluation/lease_coordinator.py` — new coordinator. Nothing imports it from a package, worker, route, or setting.
- `Backend/tests/test_evaluation_lease_coordinator.py` — anonymous SQLite regressions.
- `Backend/tests/evaluation_lease_coordinator_pg_checks.py` — opt-in, not named `test_*.py`, not executed here.
- `docs/qa/evaluation-lease-coordinator-2026-10-10.md` — this note.

No workflow, catalog, resolver, scoring, guard, model, migration, route, worker, config, cache, or UI file was edited. `JOB_KINDS` remains `pms_upload`, `report_generation`, and `story_report_generation`. `evaluation_apply` stays out of `worker.process_job_once`.

## Seams in the existing service

`capture_queued` calls `_capture(..., leave_queued=True)` and does not commit. A new row is inserted `queued` / `pending`, then the existing locked source read still confirms the fingerprint. `leave_queued` defaults to false, so public `capture` still moves that new row to `staging` / `running` inside its own commit.

`_promote(..., acknowledge_job=True)` still sets the job to `succeeded`, progress 100, and the bounded result in the same transaction as the scores, revision, and outbox. The coordinator calls it with `acknowledge_job=False`. Public `promote` does not pass the flag.

The coordinator does not call `EvaluationWorkflow.apply`, does not read `PMS_JOB_LEASE_SECONDS`, and does not publish the outbox. The dormant publisher stays separately disabled.

## Interface

`EvaluationLeaseCoordinator(db, clock=None)`. Every operation takes `enabled=False`. Only the literal boolean `True` enters the body. `False`, `0`, `1`, `"true"`, and any other object return immediately:

```text
{"enabled": false, "outcome": "disabled"}
```

That return happens before argument checks, the clock, the session, and construction of `BoundedApplyService`. A disabled call therefore does no database or client work.

When `enabled` is `True`, each state-changing call ends its own transaction and rolls back on failure. The clock, when supplied, must return an aware `datetime`. A naive value raises `LeaseCoordinatorError("invalid_clock")` before SQL. With no clock, the call uses `datetime.now(timezone.utc)`.

| Check | Accepted value |
| --- | --- |
| Lease seconds | real `int` from 1 through 3600 |
| Worker id | `str` of length 1 through 150, no whitespace or delete character, not trimmed |
| Epoch | real `int` greater than or equal to 0 |
| Period | real `int` year 2000 through 2100 and month 1 through 12 |
| Page size | existing `_page_size`: real `int` from 1 through 500; default 100 |

`True`, `False`, and floats are rejected for every integer above. Bool is not coerced to 1. There is no `OFFSET` and no scan of queued work. Start, heartbeat, stage, promote, acknowledge, recover, status, cancel, and retry all take one job id.

`LeaseCoordinatorError` is an `EvaluationError`. Its message and `data["code"]` are the same stable code. Unexpected exceptions roll back, log the static text `evaluation lease coordinator persistence failed`, and raise `persistence_failed` with no `__cause__`. The log does not include the original exception text.

## Who may manage a job

The captured requester is the only management identity. After the team row is locked, the user row is selected again with `populate_existing` and without `FOR UPDATE`. That user must still exist, have role `Admin`, be `is_active`, and equal `requested_by_user_id`. A missing, deleted, revoked, or inactive user fails closed with HTTP 403 for every caller, including the original actor dict.

Another active Admin cannot read status, cancel, retry, claim, stage, promote, acknowledge, or recover. Enqueue of an open binding by a different Admin raises `duplicate_binding` and does not replace `requested_by_user_id` or the actor snapshot. The snapshot is attribution written by capture. The role stored on the actor dict is not read back as a grant. This keeps execution from impersonating a requester who was revoked or deleted after capture, and it keeps a second Admin from taking over an immutable requester.

The same requester may enqueue again while that open row is still `queued` and `pending`. The second call returns the same job id with `resumed` true and leaves `available_at`, the requester, and the snapshot unchanged. An open `staging` or `promoting` row, including a public capture that is already `running` with no worker, raises `duplicate_binding` and commits nothing. That no-lease capture is not a worker-owned job: start and retry both raise `invalid_state` and leave it unchanged.

## Lock order and commit boundaries

The order is the existing one. Outer team fence (`lock_team_rows`, ordered by id), then the nonlocking user select, then processing job, evaluation scope, apply control, then the performance records taken by the existing stage, promote, and retry revalidation. The coordinator does not lock the user and does not lock the control before the job. Header reads use `populate_existing`. A role change that committed before the user select is visible. A commit after that select is not held off for the rest of the transaction.

| Call | Commit |
| --- | --- |
| Enqueue | One commit of `queued` / `pending`, epoch unchanged, no stage row, score, revision, or outbox. Rollback on conflict. |
| Start | One commit. The winner is `running` / `staging`, `attempt_count + 1`, worker, heartbeat, and `lease_expires_at` equal to the post-fence admission instant plus the lease seconds. |
| Heartbeat | One commit of heartbeat and lease only. Progress and epoch stay put. |
| Stage one page | Token checks and `_stage_page` share the transaction. Progress is taken from the returned staged count and is at most 99. The lease is extended. Then one commit. |
| Promote | Token checks and `_promote(..., acknowledge_job=False)` share the transaction. Scores, one revision, one outbox row, and `promoted` commit while the job stays `running` and progress stays below 100. |
| Acknowledge | A later transaction. Matching worker, epoch, `running`, and an unexpired lease. Then `succeeded`, progress 100, bounded result, worker and lease cleared. `db.info["bounded_apply_fault"] == "before_commit"` fires here, after the promotion has already committed. |
| Recover | Read-only rollback when the expected epoch does not match or the job is already terminal. A matching epoch on a still-`running` promoted job writes the same acknowledgement, including after lease expiry, and uses the same `before_commit` fault. |
| Cancel | One commit from `pending`/`queued` or `staging`/`running` to both `cancelled`. Worker and lease cleared. Stage rows, cursor, and counts stay. |
| Retry of an expired lease | Two commits, and each one samples the clock only after its own header fence. The first persists `failed` / `lease_expired` from the first sample. The second, only if attempts and current proofs still match, opens the next epoch and stores `available_at` from the second sample. A rejection in the second commit leaves the first `failed` row in place. |
| Status | Rollback. No write. |

A lease is active only when `lease_expires_at` is present and strictly later than the admission instant. Equality is expired. An already-promoted promote is a read: it returns the committed revision, writes nothing, and does not insert another revision or outbox row. A different worker is `stale_token` while a worker id is still stored.

## Admission instant

Enabled operations that use time read the clock once before any SQL. That reading is discarded when it is aware, and a naive value still raises `invalid_clock` with an empty statement list. Disabled calls return before that read.

The admission instant is a second reading, taken after the fences for that transaction are held:

- Heartbeat, stage, promote, acknowledge, start, cancel, and recover read it immediately after the team fence and the job, scope, and control header locks.
- Enqueue reads it after `capture_queued` has taken those fences and before `available_at` is stored.
- Retry has two transactions. Closing an expired lease reads the clock after the first header fence. Opening the next epoch reads it again after the second header fence. The two readings are not reused across the commit between them.

Live-lease admission and the timestamps written in that same transaction (`available_at`, `started_at`, `heartbeat_at`, `lease_expires_at`, `finished_at`) use this instant. Promote compares it before the score, revision, and outbox write. The instant is not read again at commit. A page or promotion that keeps running after admission can still commit if the clock moves during that later work. This is not a claim that the lease is revalidated at commit.

A second start whose lease expires while the header lock is waited out raises `invalid_state` and leaves the current worker in place. It does not raise `lease_held` for a lease that is already inactive at the admission instant, and it does not take the job over.

Progress during staging is 0 when nothing is staged, 99 when the staged count has reached the captured count, and otherwise `min(99, staged * 99 // expected)`. 100 is written only by acknowledgement.

## State transitions

Claim epoch 0 is a real epoch. It is not treated as missing.

1. Enqueue creates epoch 0, `queued` / `pending`, no lease. The source proof and its locked confirmation both run. No scored change is written.
2. Start of that id requires `evaluation_apply`, `queued` / `pending`, matching epochs, `available_at` at or before the clock, `attempt_count < max_attempts`, and no worker or lease. One winner moves to `running` / `staging`. A second start of a live lease raises `lease_held` and does not steal it. A start does not scan for other jobs.
3. Heartbeat, stage, and promote require the same worker id, the same job and control epoch, `running` / `staging`, and a non-expired lease. The control epoch does not change during the attempt. Stage calls the existing keyset page with the stored cursor. Formulas, admission, source, version, and lineage checks stay in that code. Stored corrections still score with `check_conflicts=False`. A direct `score_basis(..., check_conflicts=True)` still raises `target_conflict` for workbook target 40 against approved target 50.
4. Cancel of `pending` or `staging` serializes on the same team and header locks. It does not delete stage rows and does not write scores. `promoting` and `promoted` raise `invalid_state` before any write. The existing guard still forbids `promoting` to `cancelled`; this service does not weaken it. Cancellation clears the worker and lease, so the old token cannot heartbeat, stage, or promote.
5. Retry of `failed` or `cancelled` revalidates the approved version, engine, rules, proof, lineage, and locked source through the existing private methods. It does not insert a replacement control. The job epoch is flushed to `old + 1` before the control moves to `pending` with cleared cursor, counts, and revision. Previous stage rows stay under the old epoch. `attempt_count` is kept. The next start increments it. `max_attempts` exhausted raises `attempts_exhausted` before the epoch changes.
6. An expired `running` / `staging` lease is not sent `staging` to `pending`. Retry first commits `failed` with `error_code` `lease_expired`, then opens the next epoch only if the proofs still match. A null lease is `invalid_state` and is not adopted. A live lease is `invalid_state` and is not written. After the epoch advances, the old token fails with `stale_epoch` or `stale_token` and writes nothing.
7. Promotion can commit while the job is still `running`. That is the split. `acknowledge` is the worker's later success mark and requires the unexpired lease. `recover` is the requester's read of that committed promotion: the matching epoch writes the job acknowledgement even when the lease has expired; a stale expected epoch returns `revision_id` with `mutated` false and rolls back. Neither path creates a second revision or outbox row, and neither rewrites a promoted control to `failed` or `cancelled`. A fault set to `before_commit` on acknowledge or recover rolls that acknowledgement back and leaves the already committed revision and outbox row in place.

Retry drift uses the current approved version. A legal revise-and-approve that supersedes the captured version raises `stale_preview` and leaves the captured `version_id` unchanged. An engine constant change and a rules-checksum change do the same. A changed KPI actual raises `evidence_changed`. An added active revision raises `lineage_changed`. On an expired lease those checks run after the `failed` commit, so the job stays `failed` at the old epoch when the proof no longer matches.

## Status and result shape

Status returns only `enabled`, `outcome`, `job_id`, `state`, `job_status`, `claim_epoch`, `staged_count`, `promoted_count`, `stage_cursor`, `revision_id`, `progress`, `attempt_count`, and `safe_reason`. `safe_reason` is `cancelled` or `lease_expired`, or null for any other error code. The document has no employee name, KPI list, source array, actor snapshot, or raw SQL. Request and result JSON stay inside the existing 2048-character cap. The acknowledgement body is `{"outcome":"promoted","revision_id":"...","count":N}`.

## What SQLite proved before the clock rework

These two results are the earlier candidate, before post-fence admission. They are not the clock-rework gate.

From `Backend`, with `APP_ENV=test`, `DATABASE_URL=sqlite:///:memory:`, empty `REDIS_URL`, `PYTHONUTF8=1`, `JWT_SECRET=anonymous`, and the three seed flags false:

- Five modules together, `CI` cleared: **114 passed, 9 warnings, 45.39s**. Modules: `test_evaluation_lease_coordinator.py`, `test_evaluation_bounded_apply.py`, `test_evaluation_apply_foundation.py`, `test_evaluation_legacy_queue_isolation.py`, `test_processing_jobs.py`.
- The new module alone with `CI=true` and the same anonymous environment: **7 passed, 7 warnings, 6.00s**.

The seven cases cover a disabled call that never touches an exploding session or clock; coercion rejected before SQL; enqueue identity, same-requester resume, and a different Admin's `duplicate_binding`; one start, lease equality, a stale identity map, heartbeat, page progress 49 then 99, cancel before and after stage rows, retry epochs that keep the old rows, and rejection of the old token; source, engine, rules, lineage, and approval drift; revoked, inactive, and deleted users; closed Marketing, Pharmacy, CSR, both IP Final teams, Managerial, and Corporate; Coding, Submission, and Outbound July/August golden ratios through the coordinator; promotion left `running` below progress 100; `before_commit` on acknowledge and recover; idempotent acknowledgement; and a commit failure that becomes `persistence_failed` without the SQL text.

`git diff --check` on the tracked `bounded_apply.py` edit and the four new files, after a temporary intent-to-add that was reset, exited 0 with no whitespace errors. Git warned that those new files are LF and `core.autocrlf=true` will write CRLF the next time Git touches them. Public capture, stage, promote, and rollback tests in the existing modules passed with these seams at their defaults.

SQLite checks the predicates in order. It does not certify two connections racing on the team fence. The opt-in file is the reviewer's to run, sequentially, on `127.0.0.1:55432/pms_eval_review_fix16` and `127.0.0.1:55433/pms_eval_review_fix18`. It was not executed and those databases were not reset. It prepares the existing foundation seed, sets `available_at` to the injected clock, and uses two sessions, `statement_timeout` 8000ms, and a barrier. One test expects a single start winner. The other expects cancel and start to finish as `cancelled` / `cancelled`, with the score still 70 and no stage row.

## Unresolved until independent review

Phase 7C2 still owns worker registration and authenticated routes. This slice does not add a settings flag or a polling loop. Cache delivery remains the separate disabled publisher; no delivery fallback is counted as success. The largest real team is 200 and the default page is 100, so a full month is more than one page. Each page and each retry still re-reads the captured source; that repeated scan is a measured cost, not a new optimization or a production SLA. A revocation that commits after the nonlocking user select is visible only to a later transaction. Native one-winner and cancel-versus-start behavior, the composed suite, and the repeated native gates were not run in this session.

The admission instant stops at the post-fence reading. It does not cover a clock that moves after that reading and before commit, including during source revalidation, a keyset page, or promotion. SQLite regressions advance an injected clock inside the lock seam; they do not certify a PostgreSQL lock wait. The reviewer's native PostgreSQL clock probe was not executed in this rework, and databases 55432 and 55433 were not reset.

## Clock rework checks

An earlier verification of this rework was interrupted before the five-module suite and the immutable reviewer probe started. The only results from that stopped session are partial selections of the new module: 6 passed, 8 deselected, 7 warnings, 6.77s, and then 1 passed, 13 deselected, 7 warnings, 2.67s. Those selections are not the completed gate.

The completed check, after `_admit` was sampled after the fences and the helper `_replace_lock` was removed, used the same anonymous environment with `CI=true`:

- Five modules: **121 passed, 9 warnings, 56.63s**. Exit 0. The extra seven cases are the four expired-during-header-wait operations plus start/retry, enqueue/cancel, and recover timestamp coverage. The same nine warnings include the existing paged-memory warning and the existing stage-row identity warning in the manifest-guard test.
- Immutable reviewer file `D:/Projects/PMS_Dashboard/tmp/reviewer-lease-clock-20261010.py`: **4 passed, 7 warnings, 7.47s**. Exit 0. Heartbeat, stage, promote, and acknowledge each raised `lease_expired` and left the pre-call snapshot in place. That file was not edited.

`graphify update` was not run again for this rework. The earlier AST update recorded above stays as-is. Native PostgreSQL, the full backend suite, a browser, and a performance run were not part of this check.

## Checks after the code existed

`graphify update .` from this checkout exited 0 in 74.79s. The tool printed `Re-extracting code files in . (no LLM needed)` and extracted 894 uncached files. It wrote `graphify-out/graph.json`, `graph.html`, and `GRAPH_REPORT.md`: 10683 nodes, 29322 edges, 464 communities. It warned that 21 source files, including team JSON, produced zero nodes, and that one `.sql` file contributed nothing because `tree_sitter_sql` is not installed. No semantic or remote extraction was requested. `graphify-out/` is ignored by `.gitignore`, so that output is not part of the candidate diff.

After that update, `git status --short` is still only the modified `Backend/services/evaluation/bounded_apply.py` and the four untracked paths named above. HEAD remains `81d3b038ed6b0932ef6ba4c313c80d4a5d26b0e7`. Nothing is staged and nothing is committed.
