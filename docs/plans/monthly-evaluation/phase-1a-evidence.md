# Phase 1A evidence — version groundwork reconciliation

Status: **Phase 1A schema slice independently accepted, subject to CI. Phase 1 remains partial.** No production activation, no historical backfill, and no monthly settings lifecycle. The pre-existing Marketing acceptance failure remains open; the full local suite is not green.

This slice maps the existing team-configuration version contract into the ORM and adds one forward reconciliation revision so a fresh supported bootstrap and an already-migrated PostgreSQL schema expose the same usable baseline. Scoring, upload, dashboard behavior, endpoints, permissions, and frontend code were not changed.

## Scope

In:

- `TeamConfigurationVersion` mapped to `team_configuration_versions`, including coverage columns, publish snapshot columns, the team/version unique key, coverage index, check constraints, and the existing foreign keys.
- Nullable `PerformanceRecord.configuration_version_id`. Legacy rows stay null. Nothing assigns them a historical version.
- Alembic revision `f1a9c3e7d842` after `d9e4b7a2c106`.

Out:

- Monthly scope bindings, one-row-per-month uniqueness, and concurrency.
- Immutable retention, audit records, and any change to team `ON DELETE CASCADE` or actor/record `ON DELETE SET NULL`.
- Applied target, weight, direction, policy, or algorithm identity.
- Endpoints, permissions, scoring, upload, dashboard reads, and frontend.
- Edits to the historical migration chain, `scripts/bootstrap_schema.py`, or `Database/pms_scheme.sql`.
- Partition creation on the fresh ORM bootstrap. Existing partitions are preserved.

Approved decisions D-001, D-002 and D-003 govern later lifecycle work. This slice does not implement settings APIs, so it does not add or broaden any permission.

## Schema contract

The mapped table is the one already created by `8716484ca95c`, `b8f2d4a9c731`, and `c4a7b7d8f2ac`. There is no second version table and no separate coverage table.

Columns:

| Column | Contract |
| --- | --- |
| `id` | UUID primary key |
| `team_id` | UUID NOT NULL, FK to `teams(id)` ON DELETE CASCADE |
| `version_number` | integer NOT NULL, unique with `team_id` (`uq_team_config_version`) |
| `status`, `effective_month` | varchar(20) NOT NULL |
| `effective_year` | smallint NOT NULL |
| `config_snapshot` | JSON NOT NULL (not JSONB) |
| `config_checksum` | varchar(64) NOT NULL |
| `created_by_user_id`, `published_by_user_id` | UUID NULL, FK to `users(id)` ON DELETE SET NULL |
| `created_at`, `published_at` | timestamptz NULL, default `now()` when this revision creates them |
| `superseded_at`, `notes` | timestamptz NULL, text NULL |
| `effective_from_month`, `effective_from_year` | smallint NOT NULL |
| `effective_until_month`, `effective_until_year` | smallint NULL |
| `preview_snapshot` | JSON NULL |
| `total_weight` | numeric(7,4) NULL |
| `overall_score` | numeric(10,2) NULL |
| `is_active` | boolean NOT NULL, default true when this revision creates it |

Checks: `ck_team_config_effective_from_month`, `ck_team_config_effective_until_month`, `ck_team_config_effective_range`.

Index: `idx_team_config_coverage` on `(team_id, status, effective_from_year, effective_from_month, effective_until_year, effective_until_month)`. It is not a unique month constraint.

`performance_records.configuration_version_id` is a nullable UUID. The parent foreign key is `fk_performance_records_configuration_version` to `team_configuration_versions(id)` ON DELETE SET NULL. On a partitioned table the foreign key is added to the parent; PostgreSQL attaches child constraints with `conparentid` set to that parent. The composite primary key remains `(id, year)`.

`Team` ON DELETE CASCADE and the SET NULL actor/record actions are the existing contract. They do **not** satisfy an immutable-history requirement. Phase 1B has to decide retention before any delete path is treated as safe.

## Revision behavior

`f1a9c3e7d842` reads and changes only the `public` schema. The migration transaction sets `search_path` to `public`, and catalog queries, DDL, and foreign-key targets are schema-qualified. Unique keys and the coverage index are identified from PostgreSQL attribute numbers, not from definition text.

- Missing version table: create the full contract in `public`, then add the record column and parent foreign key if those are missing.
- Compatible existing objects: leave them, including extra columns and existing defaults. No `UPDATE`, `DELETE`, or backfill runs.
- Missing nullable contract column, missing complete coverage index, or missing exact `(team_id, version_number)` unique key on an otherwise compatible table: add only that object. `preview_snapshot` remains the nullable additive case covered by tests.
- Missing required columns are not repaired, even when the version table is empty. The revision fails before any write and does not query `team_id` or `version_number` when those columns are absent.
- Wrong type, nullability, primary key, exact unique column list, named unique key, check grouping, referred schema, validation state, delete action, or coverage index shape: raise `RuntimeError` before applying catalog changes. A named unique constraint on any other columns, including `UNIQUE (team_id_extra, version_number)`, is incompatible. A coverage index that is partial, expression-based, unique, invalid, not ready, or has included columns is incompatible even when its plain attribute names match. A foreign key whose referred table is not in `public`, or whose `convalidated` is false, is incompatible and is not validated or cleared. A populated `configuration_version_id` with no matching version row also fails when the foreign key is absent, and those values are not cleared.
- Repeat execution finds the repaired shape and does not add a second foreign key or coverage index.
- Offline SQL generation is refused. An unconditional script cannot tell an old ORM stamp from a migrated database.

Independent review found four detection defects. The same revision now rejects them before DDL:

1. Substring matching treated `UNIQUE (team_id_extra, version_number)` as the team/version key. Identity is now the ordered `conkey` attribute list. The named constraint is rejected when those attributes are not exactly `(team_id, version_number)`.
2. Unqualified DDL followed `search_path`. With `search_path=shadow_review,public`, groundwork was created in `shadow_review` while `public` stayed absent. Inspection, DDL, DML, and referred foreign-key schemas now address `public`.
3. A partial or expression index named `idx_team_config_coverage` counted as the coverage index when extracted attribute names matched. The index must be a valid, ready, non-unique, non-partial key with no expressions and no included columns, on the exact coverage columns.
4. An empty version table missing required columns reached `GROUP BY team_id, version_number` and could raise a raw missing-column error. Required-column repair is unsupported. The failure is a `RuntimeError` before writes.

A later review found two more false matches. Check comparison now keeps parentheses and accepts only the canonical `pg_get_constraintdef` text probed on PostgreSQL 16.15 and 18.6. `effective_until_year * (12 + effective_until_month)` is not treated as `(effective_until_year * 12) + effective_until_month`. Foreign keys match only when `convalidated` is true. A `NOT VALID` record foreign key is rejected before DDL and is not validated or rewritten.

D-003, confirmed for later phases, says an approved fixed target that conflicts with the workbook target blocks upload/commit until resolved, with no Admin override. Raw workbook evidence stays preserved. This slice does not implement that ingestion rule. D-001 and D-002 are unchanged.

Downgrade is an explicit no-op. It does not drop `team_configuration_versions`, coverage columns, snapshot columns, or `performance_records.configuration_version_id`. Those objects may already have existed before this revision, and a downgrade cannot know which rows are referenced. Normal rollback is the previous application build with the expanded schema kept. Re-upgrade after that downgrade is idempotent.

`scripts/bootstrap_schema.py` is unchanged. It still creates ORM metadata and stamps head only when the database has no tables and no `alembic_version`. Stamping head is not execution of the historical chain. The direct empty-database chain still fails at `975c072657f1`, and the historical `Database/pms_scheme.sql` chain still has its pre-existing materialized-view failure. Neither path was edited or stamped around.

## Verification

Parent process environment for ordinary tests: `APP_ENV=test` and `DATABASE_URL=sqlite:///:memory:`. PostgreSQL tests require `PMS_EVAL_SCHEMA_TEST_URL` to be exactly one of the two disposable loopback URLs and refuse every other target before connecting. They also require `APP_ENV=test`, check `current_database()`, and require the in-container `port` to be 5432. Alembic subprocesses receive that explicit URL. They do not read an implicit default.

Local interpreter: Python 3.13. Disposable servers, read after the bootstrap case: PostgreSQL **18.6** on `pms_eval_foundation18` and PostgreSQL **16.15** on `pms_eval_foundation16`. The orchestrator inventory's local server is 18.4; that database was not opened.

Review rerun, Python 3.13, after the detection fixes. Parent environment for ordinary tests: `APP_ENV=test`, `DATABASE_URL=sqlite:///:memory:`. PostgreSQL commands also set `PMS_EVAL_SCHEMA_TEST_URL` to the exact disposable URL. The full suite left that variable unset.

| Command | Result |
| --- | --- |
| `python -m pytest -q tests/test_team_configuration_version_foundation.py` with the PG URL unset | **6 passed, 16 skipped**, 13.87s |
| Same file with the PG18 URL | **22 passed**, 59.74s |
| Same file with the PG16 URL | **22 passed**, 77.20s |
| Phase 0 baseline file set, sqlite only | **64 passed, 1 skipped**, 7 warnings, 4.02s |
| `python -m pytest -q --tb=line -rs` in `Backend`, sqlite only, PG URL unset | **1070 passed, 18 skipped**, 63 warnings, 276.93s, exit 0 |

The implementer's eighteen full-suite skips are sixteen opt-in PostgreSQL reconciliation cases, the existing scoring-characterization snapshot case, and the real Marketing workbook case. The Marketing skip predicate covers either `CI=true` or a missing workbook; the generic skip reason does not prove absence. Codex independently executed that case, and it failed with 131 rows versus 68 expected. The same exact failure was reproduced on untouched primary `main` at `2af9eb1e3991cb649ebcc695e3f2c42fbce4f40a`. No assertion or skip was changed. Do not read the implementer's full suite as passing that acceptance case.

### Independent orchestrator verification

Python 3.13, `APP_ENV=test`, parent `DATABASE_URL=sqlite:///:memory:`. Only the two explicitly allowlisted synthetic targets were reset by the foundation suites. Separate review probes used task-owned review databases on the same disposable servers; every probe transaction was rolled back.

| Executed gate | Result |
| --- | --- |
| Complete foundation file, explicit PG18 target | **22 passed**, 134.61s |
| Complete foundation file, explicit PG16 target | **22 passed**, 136.13s |
| Independent schema/CHECK probes, PG18 and PG16 | Passed: exact unique, schema qualification, partial index, referenced FK schema, partial table, unvalidated orphan FK, CHECK grouping and valid range behavior |
| Full backend, PostgreSQL opt-in unset, CI unset | **1070 passed, 1 failed, 17 skipped**, 63 warnings, 250.50s |
| Exact failing Marketing case on untouched main | **1 failed**, same 131-versus-68 assertion, 4.28s |

The seventeen independent full-suite skips are sixteen PostgreSQL opt-in cases (separately run and passed above) plus the existing dataset snapshot case. This is bounded schema acceptance with a proven pre-existing acceptance-file mismatch, not a claim that every release gate passed. Resolving the authoritative Marketing workbook/expected results remains necessary before final release acceptance.

PostgreSQL cases that passed on both 18.6 and 16.15:

- Old-head ORM shape (version table and record column absent, `performance_records` not partitioned, synthetic raw/KPI/management rows present). Upgrade creates the groundwork, leaves version row count at 0, leaves the legacy link null, and does not create partitions. A second in-process upgrade does not duplicate keys. Inserted version evidence and the legacy null link survive downgrade and re-upgrade.
- Representative migrated shape (full version row, yearly partition `performance_records_2026`, default partition, parent FK, raw/KPI/management sentinels). `effective_month` stayed `July` while `effective_from_month` stayed `8`, so the old coverage month-name backfill did not run again. Payloads and management person-scope sentinels were unchanged. Parent configuration FK count stayed 1. Each partition's configuration FK `conparentid` pointed at that parent. Downgrade and re-upgrade kept the same fingerprint.
- Missing nullable `preview_snapshot` was added as null without rewriting the other version fields. The second upgrade did not add a second column.
- `config_snapshot` as JSONB failed before rewrite. The stored JSONB value and Alembic version `d9e4b7a2c106` remained.
- A record FK with `ON DELETE CASCADE` failed. The CASCADE action was left in place. It was not dropped and recreated as SET NULL.
- Supported bootstrap (`scripts/bootstrap_schema.py`, then `alembic upgrade head`) stamped the discovered current head. That head is `f1a9c3e7d842` today. Tests assert one head and that this revision's `down_revision` is `d9e4b7a2c106` and that both revisions are ancestors of the head. They do not permanently require `f1a9c3e7d842` to remain the latest head. ORM metadata has **39** tables. The disposable database then had **40** public base tables, the extra one being `alembic_version`. `config_snapshot` was `json`, the record link was `uuid`, and `performance_records` stayed `relkind=r` (not partitioned). ORM roundtrip persisted a version row, a null legacy link, and an explicit link. Setting `alembic_version` back to `d9e4b7a2c106` and upgrading again did not duplicate constraints or change those rows. Downgrade to `d9e4b7a2c106` and re-upgrade kept them.
- `uq_team_config_version` redefined as `UNIQUE (team_id_extra, version_number)` failed. Alembic stayed at `d9e4b7a2c106`. Columns, constraints, indexes, and the existing version row were unchanged, and `configuration_version_id` was not added. A second row with the same `team_id` and `version_number` could still be inserted, which shows the drifted key was not silently treated as the real key.
- After a successful repair, a second row with the same `team_id` and `version_number` raised `IntegrityError` on `uq_team_config_version`. The first row remained.
- With `PGOPTIONS=-c search_path=shadow_review,public` (probe showed `shadow_review` first), upgrade created `public.team_configuration_versions` and `public.performance_records.configuration_version_id` only. `shadow_review` relations were unchanged and gained neither the version table nor the record column.
- A parent team foreign key that referred to `shadow_review.teams` failed. The referred schema stayed `shadow_review`, and no record column was added.
- `idx_team_config_coverage` as a partial index (`WHERE status = 'published'`) and as an expression index (`effective_until_month + 0`) each failed. The index flags and version row stayed in place, and no record column was added.
- An empty `team_configuration_versions` containing only `id` and `notes` failed with `Refusing to repair` for `team_id` and `version_number`. Output did not contain `UndefinedColumn` or `does not exist`. No required column, preview column, or record link was added.
- `ck_team_config_effective_range` rewritten as `effective_until_year * (12 + effective_until_month)` failed. Alembic stayed at `d9e4b7a2c106`. The stored definition and a version ending December 2025 before a January 2026 start stayed in place. `configuration_version_id` was not added.
- After repair, the canonical range check allowed January 2026 through January 2026 and December 2025 through January 2026. The same check rejected a January 2026 start with a December 2025 end (`ck_team_config_effective_range`). The two valid rows remained.
- A record foreign key with the expected columns, `public` target, and `ON DELETE SET NULL`, created `NOT VALID` after an orphan `configuration_version_id`, failed. The orphan link, `convalidated = false`, one parent foreign key, and Alembic version `d9e4b7a2c106` stayed in place. No version row was invented.

SQLite covers the ORM metadata contract, a real version/legacy/linked roundtrip, unique and check failures, a single current head with this revision's predecessor and ancestry, offline downgrade text with no `DROP`/`DELETE`/`UPDATE`, and refusal to run the upgrade on SQLite. SQLite is not the PostgreSQL acceptance evidence.

`rtk proxy graphify update .` completed after the check and foreign-key fixes, exit 0: 8822 nodes, 23596 edges, 405 communities. It warned that 23 JSON files produced zero nodes, that `tree_sitter_sql` is not installed, and that community labels are stale relative to the new community count. Those warnings are graph coverage, not test results. `graphify-out/` stayed untracked.

## Limitations

- Fresh supported bootstrap still does not create yearly `performance_records` partitions. This revision does not invent them and does not drop them when they already exist.
- The historical Alembic chain from an empty database, and the historical `pms_scheme.sql` upgrade, remain pre-existing failures. They were not run as acceptance and were not patched.
- Downgrade will not remove version evidence, including evidence this revision itself created. Operators who need a never-upgraded schema have to restore a backup taken before upgrade. Application rollback keeps the expanded schema.
- Existing delete actions can still remove or detach version rows. That is unchanged and is not approval to delete history.
- No local, staging, or production database outside the two disposable URLs was migrated. The four local version rows described in the inventory were not read or modified.
- CI Python is 3.11. These commands ran on Python 3.13. The revision uses only 3.11-compatible syntax, but 3.11 was not executed here.
- The real Marketing workbook acceptance test fails independently with the same baseline mismatch on untouched main. Its authoritative workbook and expected results must be reconciled before release; the test was not weakened or skipped by Codex.

## Phase 1B prerequisites

Phase 1 is not accepted. Before monthly settings behavior:

1. Monthly scope bindings and concurrency. The coverage index does not stop overlapping published ranges. Exact month/scope uniqueness, NULL scope keys, and concurrent publish/apply still need a contract and tests.
2. Immutable retention and audit. Decide what happens on team, user, and version deletion. The current CASCADE and SET NULL actions are not that decision. Add the audit records the lifecycle needs, without rewriting the rows this slice preserved.
3. Applied evidence and revision foundation. Store applied target, weight, direction, and the compatible policy/algorithm identity separately from mutable current definitions. Keep raw payload and Marketing aggregation inputs. Audit `kpi_values` uniqueness `(record_id, kpi_key)` before adding a partition-sensitive evidence identity; include `record_year` in any new evidence key. Leave legacy `configuration_version_id` null unless a real provenance source exists.
4. Any later API stays Admin-only (D-001). Unsupported target/direction recomputation stays blocked (D-002). An approved fixed target that conflicts with the workbook target blocks upload/commit until resolved, with no Admin override (D-003); raw workbook evidence stays preserved. Real-workbook goldens stay an activation gate. Fresh-install partitioning, if required, is a separate bootstrap task from this reconciliation.
