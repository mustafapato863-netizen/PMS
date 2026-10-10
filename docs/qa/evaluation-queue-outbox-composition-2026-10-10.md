# Reviewed local queue isolation and dormant outbox composition

Date: 10 October 2026. Source checkpoint `81d3b03` includes queue isolation `7368007` (source `944c93d`) and dormant outbox delivery `81d3b03` (source `ccc9a6c`) on top of reviewed bounded apply/public authority and the `a4e856d` anonymous CI repair. This is local acceptance, not main publication or deployment.

## Independently executed composed gates

- Complete default backend suite, no exclusions: **1400 PASS, 1 unchanged Marketing FAIL, 1 existing SKIP, 65 warnings, 302.31s**. Artifact `D:/Projects/PMS_Dashboard/tmp/reviewer-composed-queue-outbox-full-20261010.xml`. Only `test_real_marketing_workbook_imports_with_incomplete_rows_excluded` fails its unchanged expected68 versus current private-workbook131 rows. Neither workbook nor assertion was changed. The full suite is not release-green.
- Strictly owned PostgreSQL16/18 sequential gate: **100 PASS, 7 warnings, 173.91s**. Artifact `reviewer-composed-queue-outbox-native-20261010.xml` in the same tmp directory. Breakdown: unchanged history/month-revision/upload-race/foundation/catalog72, immutable queue isolation16, actual separate-connection stale-kind8, new publisher overlap/recovery4. No concurrent scratch reset, production database or real Redis access. An initial invocation used nonexistent test paths and collected nothing; corrected discovered filenames produced this actual gate.
- Explicit anonymous `CI=true` composed authority/queue/publisher plus immutable failure-boundary probe: **115 PASS, 8 warnings, 19.38s**, artifact `reviewer-composed-queue-outbox-ci-20261010.xml`. New normal tests do not remove CI, overwrite environment at import, or require an absolute Windows checkout. This is a local CI-shaped run, not a GitHub workflow execution.
- AST-only graph refresh: **10553 nodes, 28908 edges, 470 communities**. Existing21 no-node JSON and missing SQL parser warnings retained; no LLM labeling/dependency install. No frontend source changed in this checkpoint; historical frontend/browser evidence was not rerun or relabeled as fresh.
- Actual auth-router login/issued JWT/public evaluation/performance lifecycle repeated on this source composition: **1 scenario PASS, 8 warnings, 5.72s**, artifact `reviewer-composed-queue-outbox-jwt-20261010.xml`. Promoted manifest read/replay, persisted role denial and exact latest-only rollback retain the earlier test's invariants. This is API integration, not a fresh browser run.

## Repairs and evidence boundaries

Queue first candidate passed49 checks but failed4 immutable stale-kind checks. Its mutators trusted a preloaded legacy ORM kind. The accepted rework filters current persisted legacy kind/status/worker in the job-row admission SELECT and uses `populate_existing`; generic get reloads persisted identity. Independent74 normal and24 actual PostgreSQL gates passed before composition. SQL locks only the admitted job, not Team/control/performance rows; no evaluation worker or new public job kind is activated. Commit-before-admission freshness is proved, not arbitrary transaction-wide kind/revocation serialization.

Outbox first reviewer failure-boundary result was1FAIL/3PASS: due-row selection escaped the transaction handler. Selection and empty-page handling now use the existing rollback/generic-error boundary. Independent16 normal/external cases and4 actual PostgreSQL gates passed. Additional checks cover actual commit-method failure and a later row fault that rolls back all delivery acknowledgments. The normal test import's environment mutation was removed.

Publisher remains unregistered and default-disabled; only literal `enabled=True` touches the session/client/clock. Batch limit1..25, outbox-only `FOR UPDATE SKIP LOCKED`, promoted revision scalar binding, direct injected INCR/PUBLISH, generic non-PII message, no fallback ACK, bounded retry, and committed publication identity are retained. Zero subscribers means command acceptance, not subscriber acknowledgment. Crash/DB failure after external success can repeat the increment: at-least-once, not exactly-once. Role revocation/team deactivation after committed apply does not suppress delivery. No scoring/human plans/actions/saved report bytes are rewritten by delivery.

## Still open

### Additional actual200-cohort characterization

Independent reviewer stage-only synthetic200-record checks on owned PostgreSQL16/18 passed **4 cases, 7 warnings, 24.13s**; artifact `reviewer-bounded-native-cost-20261010.xml` and four JSON results in primary `tmp`. Live score snapshots remain unchanged and the staging session identity map is empty afterward. Capture/setup and promotion are outside the timing.

| Database | Page | Traced stage seconds | SELECT | Source scans/row visits | Traced peak bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| PostgreSQL16 | 100 | 1.916 | 40 | 2/400 | 4032817 |
| PostgreSQL16 | 200 | 1.579 | 20 | 1/200 | 6748175 |
| PostgreSQL18 | 100 | 1.942 | 40 | 2/400 | 3901603 |
| PostgreSQL18 | 200 | 1.360 | 20 | 1/200 | 6740592 |

Windows process working set was sampled around page loads via the native process-memory API without installing a dependency. Sampled maxima are189550592/195190784/192135168/196460544 bytes respectively; these include baseline, setup/import and allocator history of the shared test process. They are not continuous stage peaks or isolated stage RSS. One run per cell, synthetic Coding evidence and instrumentation do not establish p50/p95, all-family behavior or production SLA. Page200 halved SQL in these runs but consumed more traced memory; earlier SQLite timing was not faster. Keep default100 until representative repeat/load/lease-recovery gates justify tuning.

The largest actual team is200. Prior stage-only synthetic SQLite/tracing measurements remain1.516s/36SELECT/two source scans at page100; page200 was not a proven latency win. Default100 and repeated whole-source drift checks remain; no production RSS/p95 SLA or source-generation optimization is claimed.

Phase7C1 lease coordinator is a separate **unaccepted** Grok4.7/xhigh candidate from this source checkpoint. It must separate queued/pending capture from lease-fenced start, reject old epochs/workers, retain previous-attempt evidence, handle cancellation/retry and promoted-before-ACK truth. Runtime worker/HTTP registration and7D UI remain separate later gates. No main push, PR, deployment, new formula/family admission, unsupported-source substitution or completion of the whole roadmap is implied.
