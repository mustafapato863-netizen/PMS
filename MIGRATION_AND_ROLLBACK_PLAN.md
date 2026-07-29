# Migration and Rollback Plan

Date: 2026-07-29

## Current migration position

- Current Alembic revision: `e4a7c1d9b520`
- Current head: `e4a7c1d9b520`
- Historical branchpoints are merged.
- No database migration is justified by the current performance evidence.

## Pre-deployment

1. Freeze the application and migration commit SHAs.
2. Confirm a restorable database backup/snapshot.
3. Run `alembic current`, `heads` and `history` against staging.
4. Restore a production-like clone and execute the full upgrade path.
5. Run data-integrity queries for uniqueness, foreign keys, nullability, partitions and configuration versions.
6. Execute application compatibility smoke tests at the new revision.
7. Exercise downgrade to the prior revision on the clone when the migration is declared reversible.

## Application-only performance changes

Configuration caching, frontend cache isolation, SQL projections, compact
response views, lazy Redis, realtime flags, and request instrumentation do not
require DDL.

Rollout:

1. deploy to staging,
2. compare response bodies and authorized record counts,
3. run the baseline harness,
4. monitor errors, latency, memory and configuration reload behaviour,
5. deploy production with a small observation window.

Rollback:

- redeploy the prior application artifact,
- clear process/Redis caches,
- restore the prior `PMS_REALTIME_MODE` / `VITE_REALTIME_ENABLED` values if the rollout changed them,
- do not downgrade the database because no schema changed.

## Future index migration pattern

Only after EXPLAIN evidence:

- create PostgreSQL indexes concurrently where supported,
- keep DDL isolated from long data backfills,
- validate index validity and query plan,
- downgrade with `DROP INDEX CONCURRENTLY`,
- document write amplification and disk requirements.

## Data migration rules

- Preserve historical periods and configuration versions.
- Backfills must be idempotent and batched.
- Never derive historical scores from the current config when an effective snapshot exists.
- Record affected-row counts before and after.
- Abort on unexpected nulls, duplicate business keys or orphaned foreign keys.

## Emergency rollback

1. Stop write traffic or disable the affected feature.
2. Capture deployment ID, migration revision and error evidence.
3. Redeploy the last known compatible application.
4. Downgrade only if the previous app cannot operate with the new schema and the downgrade was pre-validated.
5. Restore from backup only after append-only/reconciliation options are exhausted.
6. Re-run health, auth, permissions, representative dashboards and record-count checks.
