# Database Query and Index Audit

Date: 2026-07-29
Database: local PostgreSQL 18.4, `PMS_Sys`

## Schema and migration integrity

- 55 application tables are inspector-visible.
- Alembic current and head are both `e4a7c1d9b520`.
- Historical branches are merged into a single current head.
- `performance_records` is partitioned by year.
- Core uniqueness exists for employee external ID, employee/month/year record identity, KPI record/key, configuration scope, management snapshots, upload scope and user/team/level assignment.

## Measured query attribution

| Request | Query count | SQL cursor time | Request wall time | Conclusion |
|---|---:|---:|---:|---|
| Performance June | 9 | 51 ms | 607 ms | Serialization/config work dominates |
| Planning options | 16 | 207 ms | 3,405 ms | Broad record reconstruction dominates |
| Report options | 12 | 207 ms | 3,160 ms | Broad record reconstruction dominates |
| Insights June | 14 | 233 ms | 5,608 ms | Python analysis/config work dominates |

The request-level query counts include the authentication user lookup and authorization-scope queries.

## EXPLAIN ANALYZE evidence

Representative June 2026 query:

```sql
SELECT pr.id, pr.employee_id, pr.team_id, pr.month, pr.year, pr.score
FROM performance_records pr
JOIN teams t ON pr.team_id = t.id
JOIN employees e ON pr.employee_id = e.id
WHERE t.team_level = 'employee'
  AND pr.month = 'June'
  AND pr.year = 2026;
```

Observed plan:

- Partition selected: `performance_records_2026`
- Rows: 186 returned, 829 filtered
- Planning: 11.148 ms
- Execution: 2.701 ms
- Performance partition: sequential scan
- Teams: small sequential scan
- Employees: PK index-only scan
- Shared buffers hit: 731

### Index decision

Do not add a June/year index for this flow now. Scanning 1,015 in-memory rows costs 2.7 ms and SQL is below 9% of request wall time. Another index would add write, vacuum and storage cost without addressing the measured bottleneck.

## Existing index observations

The 2026 partition already carries overlapping employee/year/month, team/year/month, team/month/year, grade/year/month and team/score indexes. Several have zero observed scans in the current statistics window.

Large audit-log JSON indexes:

| Index | Size | Observed scans |
|---|---:|---:|
| `idx_audit_log_new_values` | 19 MB | 0 |
| `idx_audit_log_old_values` | 19 MB | 0 |
| audit log PK | 2.3 MB | 0 |
| audit table/record variants | ~1.8 MB combined | 0 |

Do not drop these solely from a local statistics window. Confirm production retention, query history, backup and rollback requirements first.

Observed total relation sizes include `audit_log` at 178 MB, `performance_records_2026` at 3.0 MB, `error_logs` at 3.0 MB and `kpi_values` at 1.7 MB. `pg_stat_user_tables.n_live_tup` was stale for several relations compared with exact counts, so planner statistics should be refreshed and size/count evidence must not be conflated.

## N+1 and eager-loading review

- Dashboard records use `selectinload` for KPI values, team and employee/team, avoiding a per-record relationship query.
- Planning detail uses joined/select-in loading for child collections.
- Authentication still performs one active-user query per protected request in addition to route sessions.
- Options endpoints rebuild all authorized record models even though they only need distinct dimensions. This is a projection problem, not an index-first problem.

## Index candidates requiring future evidence

No migration is authorized yet for these candidates:

- history/list filters on `error_logs`
- notification recipient unread/time filters
- upload batch/history filters
- onboarding draft owner/status filters
- plan child plan-id/order filters

Before adding any index, capture:

1. exact ORM-generated SQL,
2. production-like cardinality,
3. `EXPLAIN (ANALYZE, BUFFERS)`,
4. selectivity and write frequency,
5. before/after plan and latency,
6. concurrent index migration and downgrade plan.

## Database configuration findings

- Hosted defaults: pool size 5, max overflow 0, recycle 1800 seconds, pre-ping enabled.
- No explicit PostgreSQL connect timeout, statement timeout, lock timeout or application name is configured.
- Missing `DATABASE_URL` falls back to SQLite; production must fail fast instead.
- `pg_stat_statements` is not installed locally.

## Recommended database actions

1. Keep the current performance indexes unchanged until production-scale evidence exists.
2. Add production-safe connection and statement timeout configuration.
3. Fail production startup if PostgreSQL configuration is absent.
4. Enable `pg_stat_statements` in an authorized production-like environment.
5. Replace option-page full model loading with SQL projections/distinct queries, then remeasure before considering indexes.
