# Async evaluation: source-golden consumers and 200-person load

Date: 11 October 2026. Local branch `codex/evaluation-roadmap-closure`, following reviewed `512ec32`. This supplement closes additional **local admitted-scope** consumer/runtime evidence, not production release or additional calculation-family admission. No application calculation, permission, cache or runtime defaults changed in this review; one permanent regression test and evidence/reference updates were added.

## Executed gates

| Gate | Observed result | Boundary |
|---|---|---|
| Full anonymous CI-shaped backend | 1434 passed, 2 existing skips, 65 warnings, 298.37s | No new exclusions/skips. The new async consumer scenario is included. Four extra restored-story assertions and explicit Redis-client isolation were added after this run started and passed in the final composed run below; do not misidentify that supplement as a second full rerun. |
| Final composed runtime/consumer/cache/month-revision regressions | 43 passed, 8 warnings, 20.52s | Real Bearer login/JWT, anonymous SQLite, including final restored-story assertions and three isolated Redis-client references. Earlier43/20.33s proof is retained. |
| Restored-story assertion supplement | 1 passed, 8 warnings, 6.69s | Includes restored Story-page movement after rollback, not just preserved report definition; subsequently included in the final43-case run. |
| Native 200-person, 5-KPI runtime/warm-reader comparison | 4 passed, 7 warnings, 82.16s | PostgreSQL16/18, page100/page200, sequential disposable fixtures; allocation tracing enabled. |
| Additional untraced default-page native samples | 2 passed, 6 deliberately unselected traced/alternate-page variants, 7 warnings, 35.93s | PostgreSQL16/18, page100 only. Not a full-suite exclusion or new skip. |
| Actual HTTP/browser async correction | Passed | Real login, keyboard Apply, queued/no-write, actual worker once, polled100%, same-client Team back-navigation, confirmed rollback and Function target/weight readback. No API mocks or production writes. |

The frontend was not changed here. The latest complete frontend824/105-file/typecheck/lint/build evidence remains the separately executed [10 October final composition](evaluation-runtime-final-composition-2026-10-10.md); it was not rerun or represented as a new frontend gate.

The existing private Marketing workbook131-versus68 discrepancy remains unresolved and follows the existing CI skip policy; this green anonymous CI-shaped run does not certify that private reconciliation or admit Marketing.

## Calculation and propagation proof

The permanent `Backend/tests/test_evaluation_runtime_consumers.py` reuses the admitted anonymous Outbound source-golden fixtures. July has four indicators and August has five including Productivity. July's target is65%, not an invented55% history.

1. Explicit baseline apply pins July82.85 and August79.82. Revised August attendance target70%, attendance weight50% and Productivity weight20% are approved. Preview, approval and queue acceptance leave live scored evidence unchanged.
2. A real worker iteration executes the queued correction under its persisted active Admin requester. Completion is acknowledged at100%; August becomes79.93. July's complete API evidence and original raw source remain unchanged.
3. Warm canonical records, legacy roster, scoped summary and trend, employee history, Insights, report center/KPI health, regenerated report preview and live Story-page movement observe the new score and target/weight. Adjacent-month basis context still reports a changed/non-like-for-like scoring basis; Productivity is not invented in July.
4. Latest guarded rollback restores the complete before image and the79.82 consumers, including live Story movement. Human plan summary remains60/80/70/Draft and saved report definition remains unchanged. Saved generated artifact bytes remain covered by existing immutable-artifact tests, not newly certified by this browser scenario.

The browser independently exercises the same correction through React controls. A previously visited Team page is revisited by browser Back within the **same browser context**, without a manual refresh: target70%/weight50% and Productivity20% appear after completion;65%/60%/10% reappear after rollback. The restored Function rollup also shows65% and60%. Browser proof has zero page errors; applied screenshot was visually inspected. The prior four-width layout gate remains separate evidence, not a new responsive rerun here.

## Complete-runtime measurement

Each native sample uses200 anonymous Outbound employees and1000 KPI rows, with approved source-derived baseline and the same correction. Timing starts **after enqueue/setup** and covers the complete runtime tick: candidate selection, lease admission, staging, drift checks, promotion, success acknowledgement and one unavailable-Redis outbox attempt. It excludes fixture creation, approval and queue admission. Readers/evidence queries are outside the timer. SQL/event instrumentation remains active even in untraced samples.

| Database | Page size | Python allocation tracing | Runtime seconds | Python allocation peak | SELECTs |
|---|---:|---|---:|---:|---:|
| PostgreSQL16 | 100 | Off | 2.650 | Not measured | 117 |
| PostgreSQL18 | 100 | Off | 2.289 | Not measured | 117 |
| PostgreSQL16 | 100 | On | 8.689 | 11,251,000 bytes | 117 |
| PostgreSQL18 | 100 | On | 9.082 | 11,145,812 bytes | 117 |
| PostgreSQL16 | 200 | On | 7.815 | 17,391,866 bytes | 89 |
| PostgreSQL18 | 200 | On | 8.070 | 17,386,123 bytes | 89 |

No OFFSET was observed. With page100 the leading-FROM counters were13 PerformanceRecord,14 KPIValue,7 Employee and8 stage-row SELECTs; page200 used10/10/5/7 respectively. These are query counts, **not** total source-row visits. The whole-runtime ORM identity-map high-water was1405 in all samples, including promotion; this is not a claim of constant total memory independent of cohort size. Repeated whole-cohort source-fingerprint reads remain an explicit growth cost, and drift protection was not weakened.

Page200 saved28 SELECTs and was slightly faster under tracing, but its traced peak was approximately55% higher. Default page100 is unchanged. Single local samples, tracing overhead, simple identical source samples and concurrent unrelated local verification do not establish production p95, RSS, scalability or a latency SLA.

## Separate-process cache correctness

For every native sample, a child process maintains its own real in-memory fallback cache and fresh DB sessions. Its PID differs from the writer. Baseline summary and eight roster rows agree at79.82; a repeated read proves two real cache hits. After runtime promotion the committed DB cache identity changes and that same process observes79.93, then proves two new warm hits. After rollback identity changes again and it observes79.82 with two more warm hits.

Redis is explicitly absent; data/config versions stay0. The publisher reports one failed/unpublished delivery and retains durable retry evidence, rather than pretending an in-process fallback published. The DB-identity correctness proof is independent of Redis success. Actual Redis7 timeout/reconnect/INCR/PUBLISH/subscriber/ACK evidence is retained in [the earlier cache review](evaluation-cross-process-cache-2026-10-10.md), but **all-consumer production reconnect** is not certified by this test.

## Reproducible local artifacts and cleanup

Primary workspace `D:/Projects/PMS_Dashboard/tmp` retains:

- `reviewer-runtime-consumers-full-20261011.xml`, `reviewer-runtime-consumers-composed-20261011.xml`, `reviewer-runtime-consumers-final-20261011.xml` and `reviewer-runtime-consumers-composed-final-20261011.xml`.
- The first three consumer harness failures, unchanged XML: wrong miniature-app employee prefix, missing required plan objective, and wrong draft checksum field. These were test-setup errors, not product defects; production routing/request contracts and all substantive assertions were preserved.
- `reviewer-runtime-golden-load-pg-{first,untraced}-20261011.xml`, guarded native benchmark/reader scripts and `reviewer-runtime-golden-load-20261011/*.json`. Native execution uses only allowlisted loopback55432/55433 databases and verifies DB/user/port/public schema before reset. No parallel native reset occurred.
- `reviewer-runtime-golden-browser-20261011/proof.json`, trace, source-golden Team screenshots and same-client body captures. Fixture metadata identifies the exact closure workspace, new anonymous scratch DB and backendPID13816.

Only exact owned backend13816 and frontend41412 were stopped after command-line/parent checks. Both PIDs are absent and review ports8319/5319 are closed; worker, native readers and test processes exited. Anonymous evidence databases/artifacts remain for review. User5173/8000, private workbooks, ordinary databases and Redis state were not mutated by these new gates.

## Genuine remaining release gates

Missing approved Marketing/Pharmacy/CSR/IP Final/Managerial/Corporate source/goldens keep those calculation editors blocked, including unproven weight-only changes. More records or a green synthetic test cannot admit them. Phase9 arbitrary formulas remains out of scope.

Production schema/backup/recovery rehearsal, explicit runtime flag/operator rollout, all-team/all-role UAT, live all-consumer reconnect and agreed latency/query/RSS budgets remain separate release acceptance. Main remains `b2187144f3940e8680866e10b9fff25e480fce97`; no remote merge/push/deploy is claimed.
