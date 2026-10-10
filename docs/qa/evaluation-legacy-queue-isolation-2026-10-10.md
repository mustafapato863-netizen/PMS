# Legacy queue isolation for evaluation jobs

Date: 2026-10-10. Checkout: `C:\Users\sghd70204\.codex\worktrees\evaluation-legacy-queue-isolation\PMS_Dashboard`, base `c47943736e63db09a46d3c853b824a71ae4925fd`. No commit, push, pull request, deploy, or runtime activation. No model, migration, API, scoring, upload, configuration, or UI file was edited.

This slice is queue isolation only. It does not deliver evaluation enqueue, start, claim, retry, cancel, lease-epoch fencing, outbox publishing, or a UI runtime.

## Change

## Independent reviewer checkpoint

The reviewer read the final source diff and the complete new normally collected test module after the resumed writer exited. The immutable anonymous isolation/stale-header probes were not edited: **74 PASS, 3.33s** (59 new + 3 unchanged legacy + 8 isolation + 4 stale-header). A separate explicit anonymous `CI=true` run passed **62 tests, 3.67s**; no absolute checkout or CI-unset restriction remains in the new normal module.

The owned PostgreSQL16/18 probes were run sequentially in one reviewer process: **24 PASS, 36.13s**, artifact `D:/Projects/PMS_Dashboard/tmp/reviewer-legacy-queue-native-green-20261010.xml`. This combines the immutable16 supported-control/header isolation cases and8 actual separate-connection committed kind changes. Their baseline artifacts retained16FAIL and8FAIL/zero errors respectively. The new kind-filtered persisted admission rejects the four stale mutations on both database versions without changing the evaluation header. This proves the tested committed-before-admission boundary, not arbitrary concurrent worker or full evaluation-runtime recovery.

`git diff --check` passed. Acceptance is scoped local queue isolation. No evaluation enqueue, worker runtime, publisher activation, scoring admission expansion, main push, PR or deployment. A full composed suite remains a separate integration gate.

Public `JOB_KINDS` stays `pms_upload`, `report_generation`, and `story_report_generation`. `ProcessingJobService.create` still rejects `evaluation_apply` before insert. No evaluation runtime flag was added.

`claim_next` and `requeue_expired` keep the three-kind allowlist in the SELECT that requests `FOR UPDATE SKIP LOCKED`, and now call `populate_existing()` on that same SELECT. An evaluation or other unsupported row is not returned, locked, or transitioned. A mixed queue still claims legacy jobs in `created_at`, then `id` order. Return values stay the same: a claimed legacy id or `None`, and the count of legacy rows this call actually transitioned. Legacy lease and attempt rules are unchanged. `claim_epoch` is untouched.

`heartbeat`, `progress`, `succeed`, and `fail` admit through `_legacy_running_job`. That SELECT filters the job id, `kind IN` the three legacy kinds, and `status = running`. When the caller passes a worker id, it also filters `worker_id`. An omitted or empty worker id still matches a running legacy row for progress, succeed, and fail. Heartbeat always requires the worker id. `populate_existing()` copies the SELECT result over an already-loaded identity-map row before any column assignment. `with_for_update(skip_locked=False)` then locks only the matched `processing_jobs` row.

A kind or status change that committed before this SELECT is visible in the WHERE clause. A persisted `evaluation_apply` row produces no match, so it is not locked and not written, even when the identity map still says `report_generation`. The lock, when a legacy row matches, lasts until this transaction commits or rolls back and covers that one `processing_jobs` row. On PostgreSQL a later update of that same row waits. A commit that arrives after the SELECT is not re-read. Team, control, and performance-record rows are not locked. This is row admission for one job, not transaction-wide serialization. Uncommitted dirty identity-map state can still autoflush before the SELECT; the fix covers a committed update that was not synchronized into the identity map. SQLite ignores `FOR UPDATE`, so the anonymous tests do not certify the wait.

`get` stays a generic read by id. It uses `populate_existing()` and does not filter kind and does not lock. `serialize` and `can_view` still do not query. `can_view` returns false when the object it is given has an unsupported kind, including Admin and the requester. Because `get` reloads the persisted kind and status, the generic status path (`get`, then `can_view`, then `serialize`) sees the current row.

`worker.process_job_once` still reads through `get` and returns before payload execution, the heartbeat thread, success, failure, notification, or file cleanup when the persisted row is missing, not running, or not one of the three legacy kinds. That read does not hold the job row across the handler. `succeed` and `fail` admit again from the persisted kind when the handler finishes. The upload, report, and story branches are unchanged. The old unsupported-kind `ValueError` remains only for an allowlisted kind that has no handler; `evaluation_apply` is not allowlisted, so it does not reach that branch.

Missing and malformed ids still return before a query. Supported legacy return values are unchanged. No unsupported DML, cache, or notification write was added.

`Backend/api/routers/jobs.py` was not edited. It already refuses the response when `can_view` is false, so the generic status route cannot disclose an evaluation job. A dedicated persisted-Admin evaluation status endpoint is a later slice.

## Files and functions

- `Backend/services/processing_job_service.py`
  - `_legacy_kind_clause`
  - `_legacy_running_job`
  - `ProcessingJobService.get`
  - `ProcessingJobService.can_view`
  - `ProcessingJobService.claim_next`
  - `ProcessingJobService.heartbeat`
  - `ProcessingJobService.progress`
  - `ProcessingJobService.succeed`
  - `ProcessingJobService.fail`
  - `ProcessingJobService.requeue_expired`
- `Backend/worker.py`
  - `process_job_once`
- `Backend/tests/test_evaluation_legacy_queue_isolation.py` (new)
- `docs/qa/evaluation-legacy-queue-isolation-2026-10-10.md` (this note)

## Portability

The new test module no longer treats `CI` as a failure and no longer allowlists one absolute Windows checkout. It still refuses to import unless `APP_ENV=test`, `DATABASE_URL=sqlite:///:memory:`, and `REDIS_URL` is empty. Its fixtures stay in-memory SQLite and create only `users` and `processing_jobs`. The normal collected suite has no PostgreSQL capability. Native probes stay outside this file. `.github` and public tests were not edited. The two reviewer probe files were not edited; they still refuse `CI` and still allowlist their own checkouts.

## Gates

Anonymous environment for every run below: `APP_ENV=test`, `DATABASE_URL=sqlite:///:memory:`, `REDIS_URL` empty, `PYTHONUTF8=1`, `JWT_SECRET=anonymous`, `PMS_AUTO_SEED=false`, `PMS_SEED_PERMISSIONS_ON_STARTUP=false`, `PMS_SEED_DEMO_LEVELS=false`. Working directory `Backend`. Commands were prefixed with `rtk proxy`.

First-slice RED, before the service and worker edit, `python -X utf8 -m pytest -q -p no:cacheprovider --tb=line tests/test_evaluation_legacy_queue_isolation.py`: **19 failed, 19 passed, 3.99s**. The failures were the unwanted behaviors: `claim_next` took the evaluation row, heartbeat/progress/succeed/fail/requeue wrote it (including omitted worker ids), `can_view` returned true for Admin and the requester, expired requeue changed the evaluation header, and `process_job_once` recorded `Unsupported processing job kind` and moved the row to failed.

The first SQL assertion inspected the query object from before `with_for_update` returned. The spy was pointed at the returned statement and that one test was rerun: **1 failed, 2.98s**. The compiled statement contained `FOR UPDATE SKIP LOCKED`, and its WHERE clause still had no kind predicate.

First-slice GREEN, `tests/test_evaluation_legacy_queue_isolation.py` plus unchanged `tests/test_processing_jobs.py`: **41 passed, 2.55s**. Unchanged external probe `D:/Projects/PMS_Dashboard/tmp/reviewer-legacy-queue-isolation-20261010.py`: **8 passed, 1.73s** (baseline before the first slice was 8 failed, 4.82s).

Independent review RED after that GREEN. `D:/Projects/PMS_Dashboard/tmp/reviewer-legacy-queue-stale-header-20261010.py` preloads a running `report_generation` row with `expire_on_commit=False`, commits `kind=evaluation_apply` with `synchronize_session=False`, and then calls heartbeat, progress, succeed, and fail. The identity map still says `report_generation`. Those four fresh-source cases failed. Combined with the passing normal and isolation cases: **49 passed, 4 failed, 4.20s**. This probe checks persisted-kind freshness. It is not a native concurrency certificate. The 8 passing isolation cases did not cover it.

The reviewer also reproduced 16 genuine native baseline unsafe operations on PostgreSQL 16 and 18 before these candidate changes, artifact `reviewer-legacy-queue-native-red-20261010.xml`. This lane did not execute or reset PostgreSQL.

Freshness GREEN, `CI` unset, from `Backend`:

`python -X utf8 -m pytest -q -p no:cacheprovider --tb=short tests/test_evaluation_legacy_queue_isolation.py tests/test_processing_jobs.py D:/Projects/PMS_Dashboard/tmp/reviewer-legacy-queue-isolation-20261010.py D:/Projects/PMS_Dashboard/tmp/reviewer-legacy-queue-stale-header-20261010.py`

**74 passed, 3.21s.** Breakdown: 59 in the new file (the previous 38 plus 21 persisted-kind cases), 3 unchanged tests in `tests/test_processing_jobs.py`, 8 unchanged isolation-probe tests, and the 4 stale-header probe tests that had failed.

Same anonymous environment with `CI=true`. The reviewer probes refuse `CI`, so they were not part of this run and were not edited:

`python -X utf8 -m pytest -q -p no:cacheprovider --tb=short tests/test_evaluation_legacy_queue_isolation.py tests/test_processing_jobs.py`

**62 passed, 2.66s.**

Repository root `git diff --check` exited 0 with no findings on the tracked diff. `graphify update .` rebuilt a gitignored AST graph (10236 nodes, 27834 edges, 447 communities, no LLM). That output is not release evidence.

## What the anonymous tests show

The tests use an in-memory SQLite database and the `users` and `processing_jobs` tables only. They do not open PostgreSQL, Redis, a socket, or a product upload file. Stale-kind cases read the row back with a core `SELECT` of `processing_jobs`, so the assertion is the stored row and not the stale ORM object.

- A mixed queue with an earlier `evaluation_apply` row, a not-yet-available legacy row, and legacy upload/report/story rows claims only the available legacy rows, in `created_at` then `id` order. The evaluation column snapshot stays the same, including claim epoch, lease, progress, result, and error fields.
- The claim and requeue statements that request `FOR UPDATE SKIP LOCKED` bind exactly the three public kinds in the WHERE clause. Compiling that ORM statement as PostgreSQL text does not connect to PostgreSQL. The same kind predicate still excludes a row whose identity map says `report_generation` after the stored kind was committed as `evaluation_apply`.
- Heartbeat, progress, succeed, fail, and expired requeue issue no INSERT, UPDATE, or DELETE for a running `evaluation_apply` row, whether the worker id matches or is omitted. The column snapshot is unchanged.
- The same four mutators, with a matching worker id and with an omitted worker id where that was already legal, leave the stored row unchanged when the identity map says running `report_generation` and the stored kind is `evaluation_apply`. The admission SELECT binds the three legacy kinds. Its compiled PostgreSQL text is `FOR UPDATE` without `SKIP LOCKED` and without a join. The in-memory kind stays `report_generation` because the filtered SELECT returns no row.
- The reverse preload admits the stored kind: the identity map says `evaluation_apply` and the stored kind is running `report_generation`. Heartbeat, progress, succeed, and fail, including omitted worker ids for the last three, update that legacy row and leave `kind` as `report_generation`.
- `get` followed by `can_view` and `serialize` reloads a stored `evaluation_apply` kind and a stored non-running status. The kind read takes no row lock and does not put a kind predicate in the WHERE clause. Admin `can_view` is false for the stored evaluation kind. A stored `queued` status makes all four mutators return without writing.
- `process_job_once` on a stale identity map returns before the heartbeat thread and before executor, succeed, fail, notify, or cleanup when the stored kind is `evaluation_apply` or the stored status is `queued`. The core row is unchanged and the injected session opens once. When the stored kind is `report_generation` and the identity map says `evaluation_apply`, the existing report handler runs and succeed records that legacy row.
- Missing and malformed ids return without a SELECT. A well-formed missing id selects nothing and writes nothing.
- `can_view` is false for `evaluation_apply` and for an unknown kind, including Admin and the requester. It is still true for a legacy owner and for Admin on a legacy job.
- `create("evaluation_apply")` raises `Unsupported processing job kind: evaluation_apply` and writes no row.
- Legacy upload, report, and story still claim, heartbeat, progress, succeed, retry, and become terminal at the attempt limit. The worker dispatch still calls the existing handler, records success, requeues a retryable `RuntimeError`, and fails a non-retryable `ValueError` without cleanup.

## Not delivered

No evaluation job can be enqueued, started, claimed, retried, or cancelled by this slice. There is no control-row lease, no epoch fence, no staged apply, no outbox publisher, and no settings UI. Fresh persisted-Admin evaluation status remains a later slice. Full backend and native PostgreSQL gates were not run, including the 16 baseline unsafe operations in `reviewer-legacy-queue-native-red-20261010.xml`. These self-tests are not independent acceptance. SQLite does not certify native `FOR UPDATE`, native `SKIP LOCKED`, or evaluation controls.
