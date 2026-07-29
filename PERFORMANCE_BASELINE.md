# PMS Performance Baseline

Date: 2026-07-29
Environment: Windows local runtime, React dev server on 5173, FastAPI on 8000, PostgreSQL 18.4 database `PMS_Sys`, Redis disabled.

## Method

- Authenticated read-only requests used a short-lived JWT for an existing active local Admin.
- Secrets, token values and employee data were not recorded.
- Each HTTP endpoint was warmed once.
- Fast endpoints used five measured iterations; Insights/Teams/Uploads used three.
- `p95 observed` is the maximum observed sample, not a statistically strong production p95.
- Focused in-process probes counted SQLAlchemy cursor executions and summed database cursor time for one request.
- No production system or remote Supabase database was load tested.

## HTTP baseline

| Flow | Scope | Samples | Status | p50 ms | Mean ms | p95 observed ms | Payload bytes |
|---|---|---:|---:|---:|---:|---:|---:|
| Auth current user | `/api/auth/me` | 5 | 200 | 27.95 | 153.23 | 598.94 | 340 |
| Performance | June 2026 | 5 | 200 | 943.42 | 1,201.83 | 2,651.67 | 597,829 |
| Performance records | June 2026 | 5 | 200 | 1,397.13 | 1,819.44 | 2,961.98 | 597,829 |
| KPI weights | all authorized | 5 | 200 | 45.90 | 44.63 | 49.96 | 3,649 |
| Planning options | all authorized | 5 | 200 | 5,007.43 | 5,501.25 | 8,458.77 | 20,274 |
| Planning list | all authorized | 5 | 200 | 43.01 | 48.72 | 60.29 | 832 |
| Report options | all authorized | 5 | 200 | 3,370.72 | 3,206.56 | 3,568.62 | 33,006 |
| Report list | page 1 | 5 | 200 | 29.98 | 35.45 | 45.72 | 1,737 |
| Insights workspace | June 2026 | 3 | 200 | 6,989.40 | 6,843.64 | 8,268.26 | 487,435 |
| Team management | all teams | 3 | 200 | 94.07 | 286.36 | 682.62 | 7,557 |
| Upload history | authorized | 3 | 200 | 25.93 | 24.95 | 27.41 | 574 |

## Query-count attribution

| Flow | Wall ms | SQL queries | SQL cursor ms | Non-SQL share |
|---|---:|---:|---:|---:|
| Performance June 2026 | 606.58 | 9 | 51.07 | 91.6% |
| Planning options | 3,404.80 | 16 | 207.02 | 93.9% |
| Report options | 3,159.71 | 12 | 206.60 | 93.5% |
| Insights workspace | 5,607.91 | 14 | 233.10 | 95.8% |

The gap between SQL and wall time is direct evidence against speculative indexing as the first intervention.

## PostgreSQL plan baseline

Representative query: performance records joined to team and employee, filtered by June 2026 and employee-domain teams.

- Rows returned: 186
- Planning time: 11.148 ms
- Execution time: 2.701 ms
- Partition pruning selected `performance_records_2026`.
- PostgreSQL used a sequential scan of 1,015 partition rows and removed 829 rows.
- Employee PK lookups used an index-only scan.

At this scale the sequential scan is cheaper than another index. Reassess only after materially larger data volume or an observed production plan regression.

## Frontend build baseline

`npm run build` completed successfully in 4.00 seconds with 3,297 transformed modules.

| Chunk | Raw kB | Gzip kB |
|---|---:|---:|
| charts | 392.53 | 112.70 |
| vendor | 221.08 | 71.04 |
| app entry | 226.34 | 64.46 |
| TeamDashboardView | 185.63 | 48.76 |
| animation | 132.20 | 43.28 |
| CSS | 244.91 | 35.37 |

## Baseline limitations

- `pg_stat_statements` is not installed, so there is no historical production query distribution.
- Sample counts are intentionally small and read-only.
- Browser LCP/INP/request waterfalls require a stable authenticated browser fixture and are not claimed here.
- Upload preview, processing, promotion, rollback and report generation were not benchmarked because they mutate shared local data.
- Cold Vercel invocation, Supabase network latency and multi-instance Socket.IO behaviour were not reproduced locally.

## Reproduction commands

- Health: `Invoke-WebRequest http://127.0.0.1:8000/api/health`
- Migration state: `.venv\Scripts\python.exe -m alembic current`
- Frontend build: `npm run build`
- SQL plan: `EXPLAIN (ANALYZE, BUFFERS)` against the representative partitioned join.

The authenticated timing harness was executed inline and intentionally did not persist credentials or tokens.
