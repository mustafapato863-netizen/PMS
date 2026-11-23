# Verified local schema/catalog inventory — 2026-10-08

Observed by Codex using the primary checkout's configured PostgreSQL connection only after verifying an explicitly loopback host. Credentials were not printed, copied to the worktree, or passed to the implementer. Connection enforced `default_transaction_read_only=on`; `SHOW transaction_read_only` returned `on`. No person records, names, identifiers, tokens, configuration payloads or user grants were read/exported. This is LOCAL evidence, not production certification.

## Runtime shape

- Server PostgreSQL **18.4**. Alembic head **d9e4b7a2c106**. Physical performance_records yearly partitions exist (2020–2030 plus default).
- team_configuration_versions exists with 4 rows. Columns: id, team_id, version_number, status, effective_month/year, config_snapshot/checksum, created_by_user_id, published_by_user_id, created_at, published_at, superseded_at, notes, effective_from_month/year, effective_until_month/year, preview_snapshot, total_weight, overall_score, is_active.
- Coverage is represented by the effective-from/until columns on the version table, **not a separate team_configuration_coverage table**.
- Version PK is id; unique uq_team_config_version covers team_id/version_number. team_id FK to teams uses CASCADE; created/published user FKs use SET NULL. These existing deletion semantics require scrutiny for immutable history, not silent destructive migration.
- performance_records contains configuration_version_id (unmapped in current ORM source), position_name, region, record_payload and branch_key. Composite PK id/year; configuration FK points to team_configuration_versions(id) with SET NULL. Existing unique employee_id/month/year must be preserved/accounted for when designing multiple calculation revisions.
- kpi_values contains actual_value, target_value, achievement_ratio, weight_applied and contribution; no direction/version evidence columns. record_id/record_year reference the composite performance PK with CASCADE. Local uniqueness is record_id/kpi_key (not record_year); partition implications must be audited rather than guessed. PostgreSQL exposes partition-related FK entries too.
- Management configuration, history and snapshot tables contain existing rows. Existing person-scope columns must not be discarded or generalized away. Counts retained in local private evidence only; no contents exported.

## Actual team catalog

30 total team rows: **23 active** (16 employee-source teams and 7 management-source teams), 7 inactive historical/alias rows.

Active employee sources: Coding, CSR, Inbound, Inbound UAE, Marketing, Outbound, Pharmacy, Pre-Approvals IP Elective Dubai, Pre-Approvals IP Final Dubai, Pre-Approvals IP Final SHJAJM, Pre-Approvals IP Offshore, Pre-Approvals OP Final SHJAJM, pre_approvals_op_dubai (db_name Pre-Approvals OP Dubai), Re-Submission, Sales, Submission.

Active DB-only management sources: crm_management, finance_management, marketing_management, nursing_management, pharmacy_management, pmo_management, rcm_management.

Inactive catalog rows: Call Center, call_center_management, call_center_offshore, csr_management, pre_approval_op_dubai (singular historical alias), sales_management, sales_management_2. Treat inactivity and historical readability separately. Do not silently reactivate or double-count aliases.

The local performance_records period inventory currently shows Employee rows for January–August 2026. Operational row counts are retained locally and intentionally omitted from this public-repository document. Management monthly evidence resides in its separate snapshot path; absence from employee records is not absence from the product.

## Implications

The feature must cover the 7 real DB-only management sources, not just 16 JSON definitions. Existing local version schema matches migration groundwork but the fresh supported ORM bootstrap lacks those objects (see orchestrator-migration-preflight.md). Phase 1 needs an idempotent expand-only reconciliation migration for both shapes and a matching ORM definition. Validate disposable PostgreSQL **18** in addition to 16 compatibility where supported. No local live migration/recalculation is authorized by this inventory.

Live golden-score snapshots and production shape are not proven by these metadata/count queries. Synthetic characterization tests remain distinct from actual-data golden baselines.

## Additional read-only provenance shape check

The four local versions all have status published. Their snapshot ROOT KEYS only were inspected: grade_thresholds, kpis, schema_version, team, workbook_mapping; no performance_levels mapping. Snapshot contents, IDs, author identities and rule values were not exported. **Zero** local performance_records currently have non-null configuration_version_id. This removes the unknown non-null count gate, but does not justify filling legacy version references by guessing.
