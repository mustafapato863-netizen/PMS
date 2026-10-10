# Phase 7B reviewer delta

## Independent reviewer gates (after the implementer exited)

The complete candidate service, workflow adapters, new normal/native tests and delta were reviewed. Independent real PostgreSQL16/18 revocation probes had reproduced four unauthorized-success failures before the repair. Post-repair independent authority plus capture/stage overlap: **6 passed31.65s**; candidate native tests: **10 passed56.84s**; unchanged foundation/history/month-revision/upload-race/catalog native tests: **72 passed185.27s**. Artifacts in `D:/Projects/PMS_Dashboard/tmp`: `reviewer-bounded-authority-overlap-green-20261010.xml`, `reviewer-bounded-native-authority-green-20261010.xml`, `reviewer-bounded-foundation-regressions-20261010.xml`. Disposable database access was reviewer-only and sequential.

Normal plus immutable external contract: **40 passed335.87s** (`reviewer-bounded-normal-green-20261010.xml`). Reviewer then corrected test instrumentation ownership: the paged-memory test now stops tracemalloc only if that test started it; assertions and budgets are unchanged. Final complete default backend collection: **1257 passed,1 failed,1 skipped,65warnings343.99s** (`reviewer-bounded-full-final-20261010.xml`). Final unchanged external contract rerun after the instrumentation correction: **15 passed62.97s** (`reviewer-bounded-contract-final-20261010.xml`). The only full-suite failure remains the independently known `test_real_marketing_workbook_imports_with_incomplete_rows_excluded`, expected68 vs actual131. No tests were excluded, weakened or changed to hide it. This is not a fully green release gate.

Independent synthetic SQLite stage-only characterization (tracemalloc on, fixture/capture excluded, live score snapshots unchanged): four cases passed41.26s. Page100 at100/200/500/1000 employees:18/36/120/300SELECTs,100/400/2500/10000full-source row visits,0.615/1.516/5.844/19.367seconds,2.96/3.21/5.08/6.02MB traced Python peaks. The user's actual largest cohort is200. A separate existing-capability page200 run for200employees passed:18SELECTs,one full scan/200visits,1.658seconds,5.49MBpeak. It reduces SQL but does not show a reliable latency improvement; DEFAULT_PAGE_SIZE stays100. These are not RSS, native database timings, percentiles or production SLAs. Repeated source scans remain an explicit growth-cost gate; drift checks were not removed and no source-generation schema was introduced.

The fresh Admin guarantee is bounded to revocations visible before the post-Team SELECT, not principal serialization for the entire transaction. Worker enqueue/lease/start/reclaim/cancellation/publisher/UI remain absent. This slice is dormant bounded staging/promotion correctness with measured cost, not completed Phase7, linear-time performance acceptance or permission to deploy. The original implementer report below retains its own narrower gate boundary.

Date: 2026-10-10. Checkout: `evaluation-bounded-apply`. No commit, merge, rebase, or cherry-pick. Phase 7C and Phase 7D are still absent, so this is not a Phase 7 exit.

## Fixes

- Capture resume, stage, promote, and manifest rollback take the upload team fence before any job, scope, control, revision, or performance-record lock. Existing headers then lock processing job, evaluation scope, apply control, and only then performance records. Scalar lookups that find the team id do not use `FOR UPDATE`. Locked rows are checked against those scalars before a write. Rollback no longer locks the revision before the team fence.
- After that team fence is held, and before job, scope, control, revision, or performance-record locks, capture (new and resume), stage (including replay), promote (including a completed replay), and manifest rollback reread the persisted user. The read uses `populate_existing`, requires `role == "Admin"` and `is_active`, and does not use `FOR UPDATE` on `users`. The actor JSON role and the stored actor snapshot stay attribution. An open stage or promote still has to be the requesting user.
- A page loads existing stage rows once, by `(job, epoch, record_id, record_year)` for that page only. A conflicting replay still raises and does not rewrite the row.
- `read_manifest`, rollback, legacy apply replay, and `can_rollback` accept a manifest only when prior and applied documents agree, `promoted_revision_id` is that revision, and scope, team, level, position, year, month, version, and epoch match the control. A known stage hash for a different parent is not verified.
- Each stage or promote batch loads the approved team file once and checksums the approved rules once. Per-record rules checksums and the second config load are gone. The full source fingerprint still runs before a page is staged and before promotion. Score application builds one evidence object per record, not once per KPI.
- A completed promote replay still accepts a stale `expected_epoch` and returns the existing revision. That path does not write scores, revisions, or outbox rows. It runs only after the post-fence user reread. The stored actor snapshot is attribution. An open stage or promote still has to be the requesting user.

## Lock note for a brand-new capture

The control fingerprint cannot change after insert. A new capture therefore hashes the month once before the job row exists, inserts the job and control under the team fence, then locks and rehashes the same records. Resume of an existing job locks that job before scope, control, and records. The opt-in PostgreSQL test pauses on that resume/control lock.

## Revocation visibility

On PostgreSQL READ COMMITTED, the post-fence user SELECT sees a role change that committed before that statement, including a change committed while this transaction waited on the team row. Access is denied and the transaction rolls back, so the capture, stage, promote, and rollback paths do not write. The users row is not locked. A role change that commits after that SELECT is not held off for the rest of the transaction. SQLite does not show another connection's commit inside an already-open transaction. The SQLite regression updates the role in that same transaction and leaves the identity-map object stale. The opt-in PostgreSQL test is the two-connection form.

## Remaining complexity

`_stream_source` reads every captured record on capture, on every stage page, and on promote. Memory stays paged because each page is released. Query work does not. A 100-row page still rereads the population, and a 1,000-row run repeats that full read on each page. Bounded memory is not linear query cost. The admin reread adds one users SELECT per operation. It does not change that cohort scan. `can_rollback` and legacy manifest replay also walk the staged population. No Phase 7C worker, route, or flag is inferred from these paths.

## Gates observed in this session

Commands were run from `Backend` with `APP_ENV=test`, `DATABASE_URL=sqlite:///:memory:`, an empty `REDIS_URL`, `PYTHONUTF8=1`, and `CI` removed.

- `tests/test_evaluation_bounded_apply.py`: 25 passed, 9 warnings, 94.29s. The paged measurement is still 100 rows = 2 employee / 1 version / 3 record SELECTs, peak 2,738,288 bytes; 1,000 rows = 60 / 10 / 70, peak 5,971,729 bytes. Those record SELECT counts are the full-month fingerprint repeated on every page.
- External `D:/Projects/PMS_Dashboard/tmp/reviewer-bounded-contract-20261010.py`: 15 passed, 63.20s. That file was not edited.
- `git diff --check`: clean.

Not run here: `Backend/tests/evaluation_bounded_apply_pg_checks.py`, including `test_role_revoked_during_team_fence_cannot_mutate` and `test_existing_capture_and_stage_do_not_deadlock`, and the external native files `reviewer-bounded-revocation-pg-20261010.py` and `reviewer-bounded-lock-pg-20261010.py`. This session did not start or reset PostgreSQL. The full Backend suite was not run. The known Marketing 131-versus-68 failure is outside this delta and is still expected.
