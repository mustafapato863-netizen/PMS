# Serialization retention — independent local review

Date: 2026-10-10. Base: `5c8aa201bc8e2f585cbee569ff18d09d7b414bbf`.
Branch: `codex/evaluation-cache-performance`.

This is a bounded local checkpoint, **not production release approval**. No
main merge, remote push, deployment, production DB write, private-workbook edit,
or authentication override was performed.

## Reviewed scope and repairs

Two different uncommitted Grok candidates were discovered. The alternate QA
worktree was preserved unchanged; it was not used as the performance baseline.
The baseline measurement loads the exact committed dependency-module Git blob.

Three new deterministic regressions failed against the isolated candidate:

1. Live foreign entries prevented cleanup from reaching later expired entries.
2. Non-FIFO owned expiry order similarly stranded an expired entry.
3. TTL started before payload construction, shortening the usable cache lifetime.

The reviewer repaired these and reduced five auxiliary indexes to three:
current generation, reverse row identity, and a separate rotating expiry cursor.
FIFO capacity eviction is independent of expiry rotation. A conservative expiry
deadline skips inspection before any known expiry is due; active sweeps still
finish in bounded windows. TTL is stamped when the completed payload is stored.
Silent `RuntimeError`/`KeyError` fallback handling was removed.

The process-local capacity is 4096 entries, with four expiry inspections per
maintenance pass. These are finite bounds, **not a measured production optimum**.
There is one current digest per record ID/normalized year. Alternating older and
newer snapshots may rebuild, but each returns its own complete evidence, never
another revision's cached result. Direct private mapping mutation is only a
test-fixture compatibility path, not a public thread-safe cache API.

Full-payload digest identity, year normalization, serialized fields, scoring
formulas, applied pins, source evidence, RLS, API contracts and frontend code
are unchanged. No schema or migration was changed.

## Independent verification

- Cache retention and existing identity tests: **18 passed**. Existing identity
  tests were not altered. New tests cover revisions, year isolation, legacy
  entries, expiry fairness, capacity, warm identity, TTL, index consistency and
  concurrent revisions. No sleeps, disabled assertions or fabricated API results.
- Full backend, `APP_ENV=test`, in-memory SQLite, Redis empty, **CI unset**:
  **1167 passed, one known failure, one existing skip**, 261.20 seconds. The suite
  is **not fully green**. The unchanged external Marketing workbook contains
  131 rows, while `test_real_marketing_workbook_imports_with_incomplete_rows_excluded`
  expects 68. The same failure was present in the accepted QA base; no fixture,
  test expectation, environment skip or private workbook was changed to hide it.
- Real FastAPI/JWT/browser lifecycle passed with frontend scoped API both
  enabled and disabled. Owned anonymous SQLite fixtures and loopback servers
  only; no injected identity or production data.
- July stays 82.85. August 79.82 → applied revision 79.93 → rollback 79.82.
  Preview and approval alone do not change stored evidence. Raw source data
  remains unchanged.
- Matching evidence verified across legacy/bounded performance, summary/trends,
  employee history, Insights, report center and regenerated report preview APIs.
- Same-client SPA Team revisit and fresh JWT Team display the changed basis.
  Actual Function KPI and Employee Profile views show Attendance target
  65 → 70 → 65, weight 60 → 50 → 60, Productivity weight 10 → 20 → 10.
  API-backed driver cards retain Attendance 46.1% / -9.2%, Booking 30.1% / +13%.
- Anonymous reads return 401. Performance Team and Function Director reads
  return 200; evaluation-management operations return 403.
- Team/Function pages have no document overflow at 390, 746, 1024 and 1440 px
  in the tested light theme. The 746px Function screenshot was visually inspected.
- Diff whitespace check passed. AST graph rebuilt without LLM calls:
  9607 nodes, 26173 edges, 420 communities. Empty JSON-node and missing SQL-parser
  warnings remain.

The frontend is unchanged from the previously verified QA checkpoint (736 tests,
lint/type/build/bundle-budget gates passed there). Its complete unit/build gates
were not rerun for this backend-only delta; the actual browser workflows were.

## Resource measurements and tradeoff

Anonymous in-process serializer microbenchmark, Python 3.13.13. Seven cold/warm
samples per size; ten revisions per row for retention. After owned tests, graph
work and servers finished, two alternating baseline/candidate pairs were run.
This measures Python allocations retained by serialization, **not total RSS,
database/API latency, browser responsiveness, Redis, multi-worker load or an SLA**.

| Rows × revisions | Base entries / traced bytes | Revised entries / traced bytes | Stale reads |
| --- | --- | --- | --- |
| 25 × 10 | 250 / 699,194 | 25 / 98,197 | 0 in both |
| 250 × 10 | 2,500 / 6,935,644 | 250 / 794,826 | 0 in both |
| 1,000 × 10 | 10,000 / 27,731,292 | 1,000 / 3,121,434 | 0 in both |

For 1000 rows, retained tracked allocations fell approximately **88.7%**. Payload
byte counts are identical (37,345 / 374,170 / 1,497,670 for the three workloads).

Timing remains variable; this is **not an overall speedup claim**. Final per-run
median milliseconds:

| Rows | Base cold | Revised cold | Base warm | Revised warm |
| --- | --- | --- | --- | --- |
| 25 | 0.803–0.823 | 0.932–1.023 | 0.643–0.645 | 0.655–0.715 |
| 250 | 8.557–8.731 | 10.172–10.625 | 8.357–8.450 | 6.542–7.250 |
| 1000 | 62.046–69.633 | 62.161–71.684 | 44.044–57.904 | 45.782–46.487 |

Bounded retention adds bookkeeping, including a small cold-path cost. Earlier
alternating runs also showed substantial machine timing variation. The reliable
gain is bounded memory/revision retention without stale evidence; production
latency and capacity tuning require a separate representative load benchmark.

Measured dependency SHA256: baseline Git blob
`0942b3df7577ce5b9277c99ddea7bbce1d711a4518528f87d2da1e6d379a2336`;
final working file
`96580aa879bd8bbabaa067cb9483d2cc839cd76c43bf9bed44c3ad848e3cc1d7`.
Raw anonymous measurement/browser artifacts remain in the task's ignored `tmp/`.

## Remaining release boundaries

The Marketing acceptance-fixture mismatch remains unresolved and must be
reported or reconciled before claiming a fully green release. Disposable
PostgreSQL/migrations, every team/formula/role/page/theme, every warm SPA consumer,
multi-worker/Redis behavior, and production-built browser performance were not
verified in this lane. No global aggregation policy was changed.
