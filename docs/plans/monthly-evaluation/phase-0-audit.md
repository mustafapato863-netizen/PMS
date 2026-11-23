# Phase 0 audit — PMS-EVAL-001

Status: **partial**. The source inventory, synthetic calculation baseline, and supplied local schema/catalog evidence are recorded here. Production shape and actual-workbook golden scores remain unclaimed. No schema, API, permission, or scoring behavior was changed.

Baseline commit: `2af9eb1e3991cb649ebcc695e3f2c42fbce4f40a`. Branch: `codex/evaluation-phase-0-audit`. Machine inventory: `phase-0-inventory.json` (team names and KPI definitions only; no people, grants, or secrets).

Approved decision D-001, from `approved-decisions.md`: Admin alone manages every Evaluation Settings stage, including draft, copy, edit, validation, preview, approval, history, and apply. Performance Team draft/preview is rejected. Approval does not recalculate. Historical results stay as stored until Admin confirms an apply job. This audit does not activate that policy.

## Evidence classes

| Class | What it covers |
|---|---|
| Source fact | Tracked code and the 16 team JSON files at the baseline commit. Alembic head `d9e4b7a2c106` was computed from `revision` / `down_revision` assignments in 44 migration files. |
| Test observation | Synthetic characterization tests, plus one disposable `sqlite:///:memory:` management scorecard. These describe today's functions, including defects. |
| Orchestrator local | `orchestrator-local-schema-inventory.md` and `orchestrator-migration-preflight.md`, read-only loopback PostgreSQL 18.4 on 2026-10-08. Not re-queried in this session. Not production. |
| Inference | PostgreSQL unique-constraint NULL behavior, and that partitions exist locally while tracked migrations contain no `PARTITION BY`. |
| Unclaimed | Production schema, official workbook expected scores, and the contents/provenance of the four local version rows. A later orchestrator read-only check confirms zero non-null local `performance_records.configuration_version_id` values. |

This session did not read `.env`, did not connect to the application database, and did not migrate or seed any existing database. Pytest was started with `APP_ENV=test` and `DATABASE_URL=sqlite:///:memory:`.

## Runtime path

Synchronous `POST /api/upload/pms` (`upload.upload_pms_file`) and the queued worker meet at `DatabaseSeeder.process_uploaded_file`.

- When `settings.PMS_ASYNC_JOBS_ENABLED` is on, the route creates a `ProcessingJob` of kind `pms_upload` and returns 202. `request_json` stores filename, dry run, and uploader identity. It does not store a configuration version or checksum. `worker._execute_upload` reads the staged file and calls the same seeder.
- A successful synchronous non-dry-run calls `CacheInvalidationService.flush_all` (which also bumps `pms:version:data`) and `clear_serialization_cache`. A successful queued upload calls `bump_data_version` and `clear_serialization_cache` only. Neither path bumps `pms:version:config`. Config bumps live on team-management and bulk-operation routes.
- Dry run does not write. Job retries read the team JSON that is current at retry time.

Employee scoring inside the seeder (`seeding_service.py`, the row loop around the `performance_level == "Employee"` branches):

- Employee with a position calls `KPIService.calculate_performance_multi_team`.
- Employee without a position calls `KPIService.calculate_performance`, whose default level is Employee.
- Any other level calls `calculate_performance_multi_team` with that level.

`calculate_performance` sends a non-Employee level to `calculate_performance_multi_team` immediately. The legacy employee blocks run only for Employee rows in Inbound, Outbound, Inbound UAE, Pre-Approvals IP Offshore, and Sales. Every other employee team that reaches this function uses the file-config path. `resolve_team_config` (`config.loader`) selects level and position. It has no period argument and does not choose Marketing `period_variants`.

`calculate_performance_multi_team` (`kpi_service`) requires configured actual and target columns, then:

- If `achievement_col` is present on the row, that value is stored (values greater than 2 stay on a percent scale; otherwise they are multiplied by 100) and actual, target, and direction do not affect the achievement.
- Otherwise a zero target searches for an `{kpi}Ach%`-style column.
- Otherwise achievement is the direction-aware target ratio. The result is capped by `GLOBAL_KPI_ACHIEVEMENT_CAP` (1.0). `score_formula: baseline_80` is stored on IP Final files and is not implemented in backend Python scoring. The frontend implements it in `teamKpiAggregator.achievementFor` as `((rawActual - 0.8) / (rawTarget - 0.8)) * 100`.

Legacy employee targets:

- Inbound, Outbound, Inbound UAE, and Pre-Approvals IP Offshore use `TargetsRepository`, then `DEFAULT_TARGETS`. Workbook target cells are not the scoring input. Inbound `DEFAULT_TARGETS["Attend"]` is 0.75. The new Inbound test keeps Attend at `0.60 / 0.75` for June, July, and August while `T.Attend%` changes.
- Inbound June 2026 sets Quality weight 0 and Other 0.15. Outbound June 2026 sets Quality weight 0 and Other 0.20, and its string check also matches a value that merely contains `"June"`. Inbound UAE has no month exception. Offshore changes weights when submitted claims are zero (0.60/0.00/0.40 versus 0.50/0.20/0.30). These are one-off formula exceptions. They are not a monthly settings model. Outbound and Offshore were traced in source and were not executed by a new test.
- Sales uses `A.*` and `T.*` together when both columns exist, and otherwise the `Ach%` column. `DEFAULT_TARGETS` is not read by that block. The score caps each Sales KPI at 1.0 before weighting. Weights come from the repository.

Persistence (`seeding_service` KPI save, `KPIValue` ORM): `actual_value`, `target_value`, `achievement_ratio`, `weight_applied`, `contribution`. The baseline ORM has no direction column and no `configuration_version_id` on `PerformanceRecord`. The full row remains in `record_payload`. Marketing is scored by `MarketingImportService` before that generic fallback. Marketing is absent from `CleanerFactory.cleaner_modules`. The other upload cleaners are inbound, outbound, inbound_uae, pre_approvals_offshore, the Dubai and SHJAJM pre-approval modules, sales, pharmacy, coding, csr, submission, and re_submission.

Historical reads: `DashboardRecordService.resolve_records` caches config by `(team, performance_level, position)`. Month is not part of the key. `_normalise_kpi_values` resolves direction through `utils.kpi_direction.resolve_kpi_direction` (config over team config, persisted value, global, then higher_better). For `target_ratio` it recomputes achievement from persisted actual and target with the current direction and may call `flipped_contribution_fix`. A persisted Queries row of actual 0.60, target 0.55, achievement 1.0, weight 0.30 becomes lower_better achievement `0.55/0.60` and contribution `(0.55/0.60)*0.30` when the current definition is lower_better. The same numbers labeled August rewrite identically. For `baseline_80`, stored achievement 0.42 and contribution 0.21 stay, while direction is still replaced from config and `direction_corrected` is absent. That is observed current behavior. The desired later policy is to leave stored history unchanged until an explicit Admin apply.

`reporting_evidence_service` emits the label `configuration_version_effect`. At this commit that label is an analysis field. Application Python does not read or write `team_configuration_versions` outside Alembic. `performance_record_versions` (`a44560904be9`) is score and grade history.

Settings: `POST /api/settings/weights` and `POST /api/settings/targets` return HTTP 409. `KPIConfigurationService.list_weights` reads team JSON. `list_targets` collapses persisted employee targets to the latest `(year, month)` per team, position, and key.

Caches and consumers traced, not integration-tested:

- File loader `lru_cache` keyed by path, mtime, and size.
- Redis integers `pms:version:data` and `pms:version:config`, with an in-process fallback.
- `useTeamConfig` query key `['team-config', teamName]`, `staleTime: Infinity`.
- `usePerformanceDashboard` stale time is 2 minutes and is not period-versioned.
- `TeamDashboardView` passes `preferConfiguredWeights: isMergedTeam` into `teamKpiAggregator`, so a merged parent can replace persisted row weights with the current file weights.
- Saved reports are job kinds `report_generation` and `story_report_generation`. Planning keeps its own baseline, target, and current values. Corrective actions are a separate import. `branch_key` is authorization and attribution. No source scoring rule branches on it.

Management is a second product path. `ManagementKPIConfig` stores direction, weight, and target for one `effective_month` / `effective_year`, level, and either position or employee identifier. `ManagementKPISnapshot` stores the actual for a month and year. `ManagementKPIConfigHistory` stores old and new JSON. `build_scorecard_dataset` filters by period. `ManagementBSCService._get_or_create_team` calls `create_management_team_identity` when no management-scoped team exists. User assignment creates a management identity only when an employee team with the same logical name already exists. `TeamService.get_all_teams` lists active employee-level teams and labels a team `data_source: "Database"` when no JSON matches. A database-only employee team can appear in that API and still fail `load_team_config`.

## Catalog

Sixteen tracked JSON sources under `Backend/config/teams/`. Per-KPI columns, weights, directions, positions, and formulas are in `phase-0-inventory.json`. Synthetic parents in `utils.report_scope` are key expansions, not JSON files and not scoring configs:

- Call Center expands to call center, inbound, and outbound. Inbound UAE is standalone.
- RCM includes coding, submission, re-submission, offshore, and the UAE pre-approval sources.
- `function_team_keys("Pre-Approvals")` is UAE only and excludes offshore and coding.
- `selection_team_keys("Pre-Approvals")` adds offshore. That is a UI selection, not a grant.
- OP Final, IP Final, and IP Elective are narrower parent sets. IP Final SHJAJM and OP Final SHJAJM stay distinct sources.
- CSR, Pharmacy, Sales, Marketing, and Inbound UAE are their own functions.

The new scope tests pin the grant boundary. No permission was added. Performance Team remains in `GLOBAL_DATA_ROLES` for ordinary data view and receives no Evaluation Settings capability.

Supplied local catalog, not re-queried here: 30 team rows, 23 active, 7 inactive. Active employee sources match the 16 JSON names; the OP Dubai row has name `pre_approvals_op_dubai` and db_name `Pre-Approvals OP Dubai` (do not reverse these fields). Active database-only management storage names: `crm_management`, `finance_management`, `marketing_management`, `nursing_management`, `pharmacy_management`, `pmo_management`, `rcm_management`. Their display names and KPI payloads were not exported. Inactive rows: Call Center, `call_center_management`, `call_center_offshore`, `csr_management`, `pre_approval_op_dubai`, `sales_management`, `sales_management_2`. The inactive Call Center row and the synthetic Call Center parent are different objects. Do not reactivate aliases.

Local period inventory shows Employee evidence for January–August 2026; operational row counts are omitted from this public document and retained in local private evidence. Management evidence is populated in its separate configuration/history/snapshot tables. File Managerial and Corporate KPI sets exist on Inbound and Sales. The inspected local performance-record inventory does not show those levels in `performance_records`. Which production surface uses the file templates versus `ManagementKPIConfig` remains unproven for production.

## Schema

Migration-source facts:

- `8716484ca95c` creates `team_configuration_versions` (team, version number, status, effective month string, year, `config_snapshot`, checksum, actors) and onboarding `published_configuration_version_id`.
- `b8f2d4a9c731` adds effective-from and effective-until coverage. There is no separate coverage table. The coverage index is not a unique one-row-per-month constraint. It adds nullable `performance_records.configuration_version_id` with `ON DELETE SET NULL`.
- `c4a7b7d8f2ac` adds `preview_snapshot`, `total_weight`, `overall_score`, and `is_active` default true, without a partial unique one-active-per-scope index.
- Version uniqueness in that groundwork is `(team_id, version_number)`. It has no level, position, person, or exact-month uniqueness. Open-ended coverage can overlap.
- `team_id` FK uses CASCADE. User FKs use SET NULL. Those deletion semantics are unsafe for immutable history if a team or user row is removed. Phase 1 must not change them silently and must not cascade-delete version rows.
- Tracked migrations contain no `PARTITION BY`. The ORM comment on `PerformanceRecord` says the composite primary key `(id, year)` is for partitioning support.

Baseline ORM, source inspection only: `configuration_version_id` is unmapped; `KPIValue` has the five numeric score inputs and no direction; management config has month, year, and target; snapshots have actual, month, and year. The characterization test asserts the positive columns only, so Phase 1 can map the missing fields without breaking this baseline.

Orchestrator local shape: PostgreSQL 18.4, Alembic head `d9e4b7a2c106`, physical yearly partitions for `performance_records` from 2020 through 2030 plus a default. `team_configuration_versions` exists with 4 rows and the columns from the three migrations. Coverage is the from/until columns. `kpi_values` local uniqueness is `(record_id, kpi_key)` and does not include `record_year`. Payloads were not exported. No application writer explains the 4 rows.

Bootstrap versus chain, from the preflight, independently of this session:

- Direct `upgrade head` on an empty database fails at `975c072657f1` because `employees` does not exist. The root revision assumes a pre-existing schema.
- Supported startup is `Backend/scripts/bootstrap_schema.py` then `alembic upgrade head` (`compose.production.yml`). On a disposable empty database that path passed: 38 ORM tables, stamped `d9e4b7a2c106`, and **no** `team_configuration_versions` and **no** `performance_records.configuration_version_id`.
- Applying `Database/pms_scheme.sql` and then upgrading failed at the same revision because materialized view `mv_team_monthly_summary` depends on `performance_records.grade`. The historical chain was not stamped past that failure.

Inference, not a live `\d` from this session: PostgreSQL unique constraints treat NULLs as distinct unless `NULLS NOT DISTINCT`. `uq_management_kpi_config_scope` includes nullable `position_name` and `employee_identifier`. The check requires exactly one of them, but Phase 1 must not rely on that unique constraint as “one row per scope.” Empty scope keys for a new exact-month unique index should be `''`, not NULL.

## Synthetic baseline

Ratios are canonical 0–1. 0.55 means 55%. Tests call current production functions. They do not pretend a monthly resolver exists.

| Case | Observed result |
|---|---|
| Employee policy, higher_better, actual 0.60 | Target 0.55 → value 1.0, raw `0.60/0.55`. Target 0.65 → value and raw `0.60/0.65` (about 92.3077%). |
| Employee policy, lower_better, same actual | Target 0.55 is a miss: value and raw `0.55/0.60`. Target 0.65 is a beat: value 1.0, raw `0.65/0.60`. |
| CSR Queries via `calculate_performance_multi_team` | July target 0.55 → Queries achievement 1.0 and score 100. August target 0.65 → stored achievement `round(0.60/0.65, 4)` and score `(0.40 + (0.60/0.65)*0.30 + 0.30)*100`. Relabeling the 0.55 row as August keeps the July score. Repeating the August row keeps score, grade, and KPI rows. |
| Coding lower_better | Quality errors 0.08/0.05 → stored `round(0.05/0.08, 4)` = 0.625. Score `(0.625*0.20 + 0.50 + 0.30)*100` = 92.5. |
| IP Final Dubai Combined, file formula `baseline_80` | Without an achievement column, target 0.55 stores capped 1.0 and target 0.65 stores `round(0.60/0.65, 4)`. With achievement column 0.40, both targets stay 0.40. |
| Empty CSR row | `calculate_performance_multi_team` raises `Missing Employee KPI columns`. |
| Legacy Inbound, empty targets repository | Attend stays `0.60/0.75` across June, July, and August. June 2026 Quality weight is 0 and Other is 0.15. July Quality weight stays 0.05. |
| Sales | Raw `A.OPCensus`/`T.OPCensus` follows 60/55 and 60/65. `OPCensusAch%` 0.40 ignores a changed `T.OPCensus`. |
| Dashboard `target_ratio` | Current direction rewrites stored achievement and contribution. July and August labels rewrite the same way. |
| Dashboard `baseline_80` | Stored 0.42 and contribution 0.21 remain. Direction still becomes the current config value, without `direction_corrected`. |
| Marketing `aggregate_kpi_metric` | Rows `(20, 10)` and `(40, 30)`, weighted average on Target Value → actual 35, target 25. Changing the definition weight from 0.10 to 0.80 does not change that metric. |
| `resolve_team_config` for Account Manager | Returns the 7 default keys and still exposes `period_variants`. |
| `MarketingImportService._select_kpi_set` | Default labels at 2026-04-01 select `default`. Variant labels at 2026-08-01 select `may_2026_onward` (effective 2026-05-01, weights 0.35/0.20/0.45). |
| Management scorecard, disposable sqlite | July target 55, actual 60 → about `60/55*100`. August target 65, actual 60 → about `60/65*100`. Reading July again after the August import keeps target 55 and the July score. |

The management result is the one current path that already keeps two months apart. The employee file calculators do not.

## Coverage and recomputation

`phase-0-inventory.json` `coverage_matrix` has one row per tracked team. Consumer integration for every row is source-traced and not covered by an end-to-end consumer test. Teams without a `characterization_test` share a calculator that was executed for a sibling team; their own numbers were not executed.

| Team | Adapter | New target can recompute the stored achievement |
|---|---|---|
| Coding, CSR, Pharmacy, Submission, OP Dubai, OP Final SHJAJM, IP Elective Dubai | File `calculate_performance_multi_team`, raw actual and target, no `achievement_col` | Yes, while raw actual and target remain. OP Final also honors `missing_actual_exception=initial_rejection_only`. IP Elective carries `kpi_direction_source_teams`. Dashboard `target_ratio` reads can still rewrite history before any apply exists. |
| Re-Submission, Inbound UAE, Outbound, Offshore, Inbound employee | UAE, Outbound, Offshore, and Inbound employee are legacy blocks. Re-Submission is file scoring with `achievement_col`. Inbound, Outbound, and UAE also declare `achievement_col` in JSON, and the legacy blocks do not read it. | No for legacy workbook target cells. Re-Submission: no while `achievement_col` is present. Sales is the legacy exception below. |
| Sales employee | Raw `A.*`/`T.*` when both exist; otherwise `Ach%`. Weights from the repository. Per-KPI cap at 1.0. | Only while the raw pair is present. |
| Marketing | Importer period-and-label selection. Generic resolver returns the default set. Aggregation weight is the target value. | A fixed scoring target must stay separate from the raw target. The generic resolver does not apply `may_2026_onward`. |
| IP Final Dubai, IP Final SHJAJM | File formula `baseline_80` plus `achievement_col`. Backend scores the precomputed column or a capped target ratio. | No, until raw inputs or an explicit achievement-source policy exist, and until `baseline_80` has a backend decision. |
| Inbound and Sales Managerial/Corporate file templates | `calculate_performance_multi_team` when the caller passes that level. | Not the path that produced the local Employee record counts. |
| Seven DB-only management teams | `ManagementKPIConfig` / `ManagementKPISnapshot` by month. No JSON. | Already month-scoped. Per-KPI contents were not exported. Do not flatten them into `team_configuration_versions` without scope columns. |

## Observed behavior versus desired policy

These are defects or boundaries relative to the monthly-settings goal. The tests keep them visible. They are not the policy to preserve.

1. A month label alone does not change employee file or legacy scores. July and August differ only when the row, the repository default, or a management config row actually changes.
2. `target_ratio` dashboard reads reinterpret stored achievements from the current direction. `baseline_80` reads keep the ratio and still replace the direction label.
3. Legacy Inbound ignores workbook targets. June weight swaps are hardcoded.
4. Precomputed `achievement_col` blocks target recomputation. Frontend `baseline_80` and backend scoring disagree.
5. Marketing's scoring target also supplies the aggregation weight in some metrics; the configured scoring weight is separate. A fixed scoring-target override must not overwrite that original aggregation input. The generic resolver ignores the period variant in the tree.
6. Settings cannot edit weights or targets (HTTP 409). Uploads do not publish a config version. Merged dashboards can overlay current file weights. Team-config queries do not expire within a session.
7. `team_configuration_versions` is unused by application code. Fresh ORM bootstrap does not create it. The local migrated database has it, four rows, and an unmapped FK column.
8. Management monthly configs already isolate periods. Employee evidence does not point at a configuration version in the ORM.

Desired end state, not implemented: exact-month published rules, stored applied target, weight, direction, and algorithm identity, raw payload preserved, history unchanged until Admin apply, workbook mode unless an explicit fixed target is chosen.

## Phase 1 reuse contract

Phase 1 reuses `team_configuration_versions` and the management month tables. It does not add a second version table, does not backfill direction from today's files, and does not recalculate history.

Reconcile both shapes with one idempotent expand-only migration, proven on disposable PostgreSQL 18 and 16:

- Legacy-migrated shape: the version table, coverage columns, and `performance_records.configuration_version_id` already exist, and local partitions exist. Add missing scope columns. Do not drop the four version rows and do not rewrite their snapshots.
- Fresh bootstrap shape: `bootstrap_schema.py` plus head creates neither the version table nor the record FK. The migration must create them. Do not “fix” this by stamping head or by calling `create_all` and calling that a chain test.
- Direct empty `upgrade head` and the historical `pms_scheme.sql` upgrade are pre-existing failures. They are not evidence that production startup is broken, and they are not Phase 1 acceptance. A historical-chain repair stays a separate reviewed task.

Exact published scope, after the live columns are confirmed on the disposable migrated fixture:

- Add `performance_level`, `position_key` text not null default `''`, `person_key` text not null default `''`, `reporting_year`, and `reporting_month`.
- These are proposed schema contracts, not approved new person-specific overrides. Preserve existing management person scopes only; do not expose new employee/person overrides in this release. Unknown legacy scope/month must remain unclassified rather than being guessed or making old versions eligible for the new exact-month resolver.
- One active published row per `(team_id, performance_level, position_key, person_key, reporting_year, reporting_month)`.
- An open-ended `effective_until` must not win over an exact month. If both match, fail closed.
- Map `configuration_version_id` on the `PerformanceRecord` ORM only as part of that reconciliation. Keep the composite primary key `(id, year)`. Do not drop local partitions. Audit the `kpi_values` unique key `(record_id, kpi_key)` before adding a partition-sensitive FK; include `record_year` in any new evidence identity.
- Store applied direction and provenance in expand-only nullable columns or a side row keyed by `(record_id, record_year, kpi_key)`. Unknown legacy provenance stays null and labeled unknown.
- Leave `ON DELETE SET NULL` and team CASCADE as they are in this migration. Immutable history needs an explicit later decision. Do not delete version rows.
- This FK-preservation proposal does not waive the immutable-history requirement: before approval/activation is enabled, team/version deletion paths must be reviewed and prevented from destroying published evaluation evidence. Any FK/retention policy change requires explicit review and tests, not an unnoticed destructive migration.
- Leave management tables month-scoped. Link a snapshot to a configuration version only with a nullable column after that column is in the reconciled migration. Do not copy the seven database-only teams into JSON.
- `performance_record_versions` stays score history.
- Preserve `record_payload` and the Marketing raw target that `aggregate_kpi_metric` uses as an aggregation weight.

Server enforcement of D-001 belongs to the lifecycle phase. Phase 1 does not grant Performance Team any settings capability and does not seed new role permissions.

## Decisions still open

D-001 is decided. These remain proposals:

- Workbook mode is the default. A fixed target is an explicit opt-in and blocks on conflict with workbook target cells.
- Copy forward is explicit. It never happens because a new month was opened.
- Branch is not a scoring scope unless a later audit shows live branch-specific targets.
- `baseline_80` needs a product decision before IP Final target or direction edits. Backend scoring does not implement it today.
- Allowed retrospective months and any operational period lock are unset.
- The four local version payloads are unknown, so they cannot be treated as recoverable historical rules.

## Later tests, not Phase 0

UI copy, weight-approval blocking, fixed-versus-workbook conflict, varies-by-person UI, every live database team, concurrency, publish without recalc, rollback, auth and revocation, Redis period keys, saved report artifacts, budgets, and a disposable PostgreSQL migration that covers NULL scope keys, overlapping coverage, and partition FKs. SQLite does not prove those constraints. The pre-existing acceptance-workbook failure (131 versus 68), which also fails on untouched main, stays untouched.

Also still unimplemented as tests: generic resolver period selection, backend `baseline_80`, recomputation when only an `achievement_col` exists, merged-dashboard `preferConfiguredWeights`, and official July/August workbook scores.

## Test outcomes from this slice

Command, from `Backend`, with `APP_ENV=test` and `DATABASE_URL=sqlite:///:memory:` set in the process before pytest:

`rtk proxy python -m pytest -q tests/test_evaluation_baseline_scoring.py tests/test_evaluation_baseline_history.py tests/test_evaluation_baseline_marketing.py tests/test_evaluation_baseline_scope.py tests/test_evaluation_baseline_management.py tests/test_function_access_scope.py tests/test_dashboard_record_config_resolution.py tests/test_config_loader_cache.py tests/test_scoring_characterization.py tests/test_scoring_engine.py --tb=line`

Result: **64 passed, 1 skipped, 7 warnings, 2.91s**. The skip is the pre-existing `test_scoring_characterization.py:182` local-dataset snapshot, left unchanged. The 20 new tests are inside the 64. Warnings are existing Pydantic v1 validators in `models/team_models.py`.

The new history test no longer asserts that `configuration_version_id` is absent, and no new test asserts that a function lacks a month or period parameter. Scoring numbers, the historical rewrite, Marketing aggregation, grant boundaries, and the management July/August split remain asserted.

Orchestrator-reported full local backend suite, not rerun here: 1064 passed, 1 pre-existing acceptance-workbook failure (131 versus 68) that also fails on untouched main, and 1 skip. That case was not modified or skipped.

## Gates before Phase 1 acceptance

1. Production schema and catalog are uninspected.
2. Official workbook golden scores are absent. The synthetic 0.60 / 0.55 / 0.65 results are the calculation contract only.
3. Contents and provenance of the four local `team_configuration_versions` rows are unknown.
4. Resolved by later orchestrator metadata check: zero local records have non-null `configuration_version_id`. Version snapshot root keys/statuses are supplied without content; no legacy rule backfill is justified.
5. Display names and KPI lists for the seven management teams were not exported.
6. `baseline_80` is undecided.
7. Historical Alembic roundtrip is not green. Phase 1 must still pass the supported bootstrap shape and a legacy-migrated disposable shape without touching the current local database.

Production certification and official workbook goldens are rollout/scoring gates; this audit alone does not authorize treating them as passed. Schema-only work can be proposed as an isolated draft once its specific data-preservation contracts are reviewed, but no historical recalculation or production deployment follows from the partial audit.
