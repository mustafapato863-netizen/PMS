# Monthly Evaluation Settings — Integrated Implementation Plan

**Document ID:** PMS-EVAL-001
**Version:** 1.1
**Date:** 2026-10-09
**Status:** Candidate implementation under independent review and correction. Phases 0–8 are not accepted as complete; unsupported scopes remain disabled until their gates pass. No production readiness or deployment verification is claimed. Phase 9 formula editing is a separate release.
**Source baseline:** main `2af9eb1e3991cb649ebcc695e3f2c42fbce4f40a`; reviewed candidate `848f601c4595b8f69f15665c7841d7714329e674`.
**Business owner:** PMS administrator
**Initial scope:** Monthly KPI targets, scoring weights and direction, connected to the entire PMS calculation and reporting pipeline.

## 1. Purpose and success definition

Administrators must be able to change a team's evaluation settings for a reporting month without changing backend code or redeploying the application. Every affected result must use the correct settings for its team, source identity, performance level, position and period.

This is a calculation-platform change with a settings interface, not a standalone editor. A successful release connects configuration to ingestion, persisted KPI evidence, team and employee dashboards, BSC, function/corporate rollups, risk flags, insights, exports, reports and relevant planning evidence.

Synthetic acceptance example: July attendance target is 55%; August target is 65%. July remains scored using 55%; August uses 65%. Opening July after publishing August must not change July's scores, targets, weights, direction, grades or displayed meaning. This is not the supplied Outbound source chronology: its attendance target is 65% in both July and August 2026.

The first release preserves existing formulas, aggregation methods, grade thresholds, missing-value rules and achievement caps. Direction is editable within supported scoring policies; a direction change does not authorize changing the policy itself. Custom formulas are a later, separate phase.

### Non-negotiable completion criteria

- All real scoring teams and supported level/position scopes appear in a live, database-connected catalog, including teams created after this release.
- New scoring runs pin an approved configuration version and retain all applied evidence.
- All consumers resolve historical evidence by its pinned version, not today's configuration.
- July/August configuration changes can be made in the UI, applied through the actual upload/calculation workflow and verified across all affected views.
- Publishing rules does not silently recalculate existing records.
- No permissions are widened; function/branch/region/team/self restrictions remain enforced server-side.
- No team is marked supported merely because its name appears in a dropdown.

## 2. Confirmed scope, boundaries and recommended defaults

### Confirmed by the business discussion

- Start with target, weight and higher-is-better / lower-is-better direction.
- Organize configuration by reporting period and team, including applicable performance levels and positions.
- Support copying the previous month's settings, previewing differences and approving a version.
- Keep old results and settings traceable.
- Integrate with the whole system, not just Administration.

### Approved decisions governing implementation

- D001: Admin alone manages every evaluation-settings stage, including catalog, draft, preview, export, jobs, approval, apply and rollback. Performance Team retains ordinary operational reads, not evaluation-management rights.
- D002: Temporarily block target/direction changes for unsupported formula paths. Weight-only changes require trustworthy achievement provenance and unchanged policy/cap; otherwise the scope remains blocked. A recognized direction or importer name is not proof of calculation support.
- Exact-month bindings are preferred. Copying rules forward is explicit; no hidden use of the latest or a future month.
- Existing workbook-sourced targets remain workbook-sourced during compatibility migration. Administrators explicitly switch selected KPIs to approved fixed targets.
- D003: A conflicting workbook target under fixed-target mode blocks upload until the mismatch is resolved. There is no acknowledgment or silent-override bypass.
- D004: Support the original August 2026 Outbound Productivity KPI at 10% with Attendance at 60%, preserving July's four scored KPIs and Attendance at 70%. Productivity is a stored source actual, not a formula derived from available time. Missing Productivity cannot be zero-filled, omitted, inferred from a final score, or resolved by renormalizing other weights.
- D005: Admin can revise the targets and weights for an already approved reporting month. Start a new draft copied from that month's approved version, preview and approve the correction, then explicitly apply it. Retain the original approved version and results/audit evidence; D002 capability limits and stale-source rollback protections still apply. This is not permission to mutate approved snapshots in place or automatically rescore history.
- Scoring does not change until a new upload or an explicit apply/recalculation operation activates the new basis.

These are approved implementation requirements, not claims that the current candidate or production already enforces them. Original July formula certification and unsupported formula-family activation remain separate evidence gates.

### Out of scope for the initial release

- Arbitrary formula/code entry, new formula families or editable grade bands/caps.
- Redesigning unrelated settings sections, all dashboards or account settings.
- Renaming database source teams, broadening grants or changing organization hierarchy.
- Automatic rewriting of old action plans, manager notes, report artifacts or corrective-action history.
- Automatic employee-specific or branch-specific overrides where no such attribution exists.

## 3. Current-system audit and why a UI-only change is insufficient

The following findings are verified from repository source. Production schema, row counts and historical configuration recoverability have not been audited in this planning task.

| Area | Verified current behavior | Required integration change |
|---|---|---|
| KPI settings | `KPIConfigPanel` reads weights/targets. Settings POST endpoints reject edits. Targets are projected from persisted employee evidence; weights come from team files. | Replace read-only inspection with a period-aware workflow backed by real calculation configuration. |
| Employee ingestion | `/api/upload/pms` calls `DatabaseSeeder.process_uploaded_file`, directly or through a queued job. It selects legacy/config-driven `KPIService` paths. | Resolve and pin the same effective configuration in preview, commit and background execution. |
| File definitions | Team JSON contains weights, direction, source columns, aggregation and position definitions; some positions have period variants. | Preserve file definitions as baseline technical templates, not mutable monthly business settings. |
| Workbook evidence | Targets and some precomputed achievement values are read from workbook columns. | Specify target and achievement sources explicitly. A precomputed achievement cannot silently bypass an edited target/weight/direction. |
| Persisted employee evidence | `KPIValue` stores actual, target, achievement, applied weight and contribution, but not direction. `record_payload` retains normalized/raw evidence. | Add complete applied-basis provenance and historical definition resolution. |
| Historical reads | `DashboardRecordService` resolves current config by team/level/position; its config key does not include the reporting period. | Use pinned version/snapshot for new records, with an isolated legacy compatibility adapter. |
| Existing version groundwork | Migrations already create `team_configuration_versions`, coverage fields and `performance_records.configuration_version_id`. Search found these references in migrations, not an integrated ORM/runtime resolver. | Inspect the real schema and reuse/repair this groundwork instead of creating a competing version subsystem. |
| Management BSC | Separate `ManagementKPIConfig`, history and `ManagementKPISnapshot` tables carry monthly settings and values. | Adapt these paths to the same effective-evaluation contract; do not discard their existing scope/history. |
| Reports/insights | Multiple services resolve definitions/direction. Reporting evidence can correct legacy opposite-direction contributions during reads. | New pinned records must not be silently reinterpreted or rescored using current definitions. |
| Frontend aggregation | Team/BSC/executive consumers use configured metadata; some paths prefer configured weights. | Remove current-config overrides for pinned historical data, while preserving proven aggregation behavior. |
| Config cache | `useTeamConfig` uses team-only query keys and `staleTime: Infinity`; backend dashboard cache already has data/config version tokens. | Add period/scope/basis identity and coordinated invalidation without losing authorization isolation. |

### Source map for implementation

| Responsibility | Existing entry points to inspect/change |
|---|---|
| Administration | `Frontend/src/components/settings/KPIConfigPanel.tsx`, `SettingsLayout.tsx`, `settingsUtils.ts`, `types.ts`; `Frontend/src/pages/SettingsView.tsx` |
| Config inspection/API | `Backend/services/kpi_configuration_service.py`, `Backend/repositories/kpi_configuration_repository.py`, `Backend/api/routers/settings.py`, `config.py` |
| Team inventory/onboarding | `Backend/services/team_service.py`, `team_onboarding_service.py`, `Backend/api/routers/team_management.py`, `Backend/models/models.py` |
| Definition loading | `Backend/config/loader.py`, `Backend/config/teams/*.json`, `Backend/utils/kpi_direction.py` |
| Upload/calculation | `Backend/api/routers/upload.py`, `Backend/services/seeding_service.py`, `kpi_service.py`, `Backend/data_cleaning/cleaner_factory.py` |
| Engine/aggregation | `Backend/services/scoring/engine.py`, `Backend/services/kpi_aggregation.py`, `balanced_scorecard_service.py` |
| Persistence/history | `Backend/models/models.py`, employee/SQL performance repositories, `Backend/migrations/versions/8716484ca95c_add_team_configuration_versions.py`, `b8f2d4a9c731_add_configuration_coverage.py`, `c4a7b7d8f2ac_add_management_publish_snapshot_fields.py` |
| Employee/dashboard reads | `Backend/services/dashboard_record_service.py`, `performance_dashboard_read_service.py`, `Backend/api/routers/performance.py` |
| Managerial/Corporate | `Backend/services/management_bsc_service.py`, management upload endpoints/templates, `Frontend/src/components/balanced-scorecard/managerSnapshots.ts` |
| Evidence/analysis/reports | `Backend/services/reporting_evidence_service.py`, `insights_service.py`, `analysis_service.py`, `report_service.py`, `reports_center_service.py`, `Backend/exports/report_exporter.py` |
| Frontend consumers | `Frontend/src/hooks/useTeamConfig.ts`, `usePerformanceData.ts`, `Frontend/src/hooks/api/usePerformanceDashboard.ts`, `Frontend/src/features/team/teamKpiAggregator.ts`, `Frontend/src/components/balanced-scorecard/scorecardAggregations.ts`, executive/function/team/profile/BSC pages |
| Hierarchy and scope | `Frontend/src/features/executive/functions.ts`, `Frontend/src/lib/directorScope.ts`, `Backend/api/dependencies.py`, `Backend/api/middleware/rbac_middleware.py`, scoped performance catalog/repositories discovered in Phase 0 |
| Cache/jobs | `Backend/services/cache_invalidation_service.py`, processing-job service/worker, frontend query/cache and upload-job state |
| Planning/actions | `Backend/services/planning_service.py`, corrective-action service, frontend planning/action views |

Paths identify integration seams, not a claim that every implementation file has already been exhaustively reviewed.

## 4. All-team and organization coverage

### Catalog identity

Build the editor catalog from actual database teams and supported scoring scopes, enriched by file templates, management configuration, existing records and canonical identity mappings. Use stable IDs internally; names/slugs are display and compatibility identifiers only.

Do not use a hardcoded list as the authoritative catalog. File-only definitions with no live team are visible as unlinked baselines, not falsely shown as configured live teams. DB-only teams remain visible with an explicit readiness status. Deactivated teams remain accessible in history.

Each scoring scope records:

- Source team ID and logical team identity.
- Employee / Managerial / Corporate level where actually supported.
- Canonical position/workstream ID or an explicit no-position scope.
- Existing person-specific management scope where applicable; do not invent employee-level personal overrides in release one.
- Branch/region attribution when reliably available, plus function membership for navigation and authorization.
- Supported importer, scoring policy, KPI definition set and configuration readiness.

Initial business-rule scope is team + level + position/person + reporting month. Branch/region remain authorization/selection dimensions unless Phase 0 proves a distinct scoring scope is required. No ambiguous branch override is permitted.

### Minimum regression inventory from the tracked baseline

| Source definition | Required fixture/coverage |
|---|---|
| Inbound | Workbook target/precomputed attendance paths; its configured management levels |
| Inbound UAE | Separate source identity; branch-attributed call-center evidence |
| Outbound | Workbook targets, weights and precomputed achievement behavior |
| Sales | Employee KPIs and configured managerial/corporate levels |
| CSR | Its own function and scoped source records; no accidental Call Center reassignment |
| Pharmacy | Its own function, ratio/source aliases and aggregation |
| Coding | Lower-is-better and mixed KPI definitions |
| Re-Submission | Lower-is-better errors/rejections and source aliases |
| Submission | Rate/ratio inputs and direction-aware scoring |
| Marketing | Every discovered position, period variant, mixed currency/count/% units and target-based aggregation input |
| Pre-Approvals IP Elective Dubai | Position/workstream definitions and special-case scoring |
| Pre-Approvals IP Final Dubai | Source-level definition and positions |
| Pre-Approvals IP Final SHJAJM | Distinct source identity, not merged-away evidence |
| Pre-Approvals IP Offshore | Offshore source scope under RCM; preserve legacy narrow-grant exclusions |
| Pre-Approvals OP Dubai | Source-level definitions and ratio inputs |
| Pre-Approvals OP Final SHJAJM | Distinct source identity and positions |
| Every DB-only management/new team | Dynamic catalog + importer/engine readiness + real integration fixture |

This is the minimum file-based inventory, not the complete live database inventory. Phase 0 must reconcile all real teams and scopes before rollout.

### Hierarchy rules

- Pre-Approvals is an RCM parent/team grouping with source sub-teams, not a new independent function.
- Pharmacy, Sales and CSR retain their current standalone function behavior.
- Merged IP Final / OP Final and other parent views retain each source record's configuration identity.
- Parent/function bulk editing is a convenience: show the exact child scopes, create explicit child drafts and approve them atomically. No hidden parent-rule inheritance in release one.
- Derived parent/function totals reuse authorized child evidence; they do not create duplicate employee rows or independently invent child weights/targets.
- Selecting a broader grouping never expands permissions. Unknown/ambiguous team or position mappings fail with a visible coverage issue.

## 5. Target architecture and canonical contracts

```text
Real team/scope catalog + baseline technical definitions
                         |
Monthly draft -> validate -> preview -> approve immutable configuration
                         |
Upload/apply request -> authorized effective resolver -> pinned calculation basis
                         |
Existing scoring engine -> persisted applied KPI evidence + calculation revision
                         |
Shared read/evidence contract
                         |
Team / Employee / BSC / Function / Executive / Risk / Insights / Reports / Exports
                         |
Revision-aware cache invalidation and comparison-basis warnings
```

### 5.1 Central services

Introduce narrow services/repositories rather than duplicating logic in every page:

1. **EvaluationCatalogService:** real teams/scopes, readiness and baseline definitions.
2. **EvaluationConfigurationService:** drafts, validation, differences, approval and immutable history.
3. **EffectiveEvaluationResolver:** authorized scope + reporting period -> one deterministic configuration; pinned record basis -> historical configuration.
4. **EvaluationPreviewService:** invokes the same engine as commit, against immutable input evidence, without writes to performance results.
5. **EvaluationApplyService:** controlled recalculation/revision activation, job progress, atomic promotion and cache invalidation.

Names are proposed. Reuse existing implementations where their contracts fit.

### 5.2 Configuration versus applied evidence

An approved configuration describes rules. A calculation snapshot describes what was actually used for a particular row. They are related but not interchangeable, especially when targets come from workbook rows.

Proposed configuration metadata:

- Immutable version ID, scope ID, reporting month, revision number, status and checksum.
- Baseline definition/policy fingerprint, source/parent version and change reason.
- Created/approved actor and timestamps.
- KPI entries: stable key, target mode/value/unit, normalized scoring weight and direction.
- Existing policy/aggregation/grade metadata retained as read-only pinned references.

Proposed applied basis for each scored record/KPI:

- Configuration version ID, calculation revision ID and input-data revision/checksum.
- Applied target, actual, weight, direction, achievement and contribution.
- Target source, achievement source, policy ID/version, unit/scale and source KPI key.
- Required aggregation definition/input references, including numerator/denominator and aggregation weights.
- Source team, level, position/person, period and validated branch/region attribution.

Persist applied direction and sufficient definition metadata. Changing labels or direction in the current file must not alter the meaning of historical evidence. New provenance may use an immutable configuration snapshot plus relational applied values; choose the final layout after the real-schema audit.

### 5.3 Reuse existing database groundwork

- Inspect Alembic heads, actual tables, constraints, indexes, nullable/partition columns and existing version rows in Local/Staging before deciding the migration.
- Reuse/extend `team_configuration_versions` and its existing record linkage if sound. Add missing ORM/repository support rather than creating an unrelated `evaluation_versions` implementation.
- Existing effective ranges need explicit semantics. Prefer month-specific bindings to immutable versions; do not mutate a version's rules when copying into the next month.
- Maintain one active configuration pointer per exact scope/month and one active calculation revision per committed scope/month population.
- Enforce uniqueness at the database boundary as well as in services. Nullable position/person/branch fields require explicit normalization or appropriate null-aware indexes; ordinary nullable unique columns can admit duplicates. Verify supported syntax against the deployed PostgreSQL version. [PostgreSQL constraints](https://www.postgresql.org/docs/18/ddl-constraints.html)
- For existing coverage ranges, enforce valid endpoints and prevent ambiguous active overlaps. Do not allow the old open-ended coverage mechanism to silently defeat exact-month selection.
- Preserve `PerformanceRecord`'s partitioned composite identity `(id, year)` when adding revision/provenance foreign keys.
- Do not cascade-delete configuration/audit evidence referenced by historical results. Team deactivation is not history deletion.
- Use fixed-precision numeric fields, explicit validation and deterministic rounding.
- Add any recalculation staging/revision/outbox tables only when existing record-version/job infrastructure cannot safely satisfy the contract.

### 5.4 Target/source and unit contract

Two initial target modes:

| Mode | Scoring target | Workbook handling |
|---|---|---|
| Workbook evidence | Validated target from the correct row/column | Keep original value and unit; preserve legitimate per-person differences. |
| Approved fixed target | Value from the approved scope/month configuration | Record workbook target separately and expose conflicts before commit. |

- UI input `65%` is explicitly percentage-scale; storage uses the existing canonical normalized scale where applicable (`0.65`). Display July `55%` and August `65%`.
- Units are inherited and read-only initially. No currency/count/% conversion through an unlabeled number or heuristic such as “greater than one means percent.”
- Weight entry is displayed as percent and stored canonically as a decimal; sums and tolerances are validated against the current scoring policy.
- Active scored weights must sum to 100% for each complete scorecard scope. Preserve legitimate zero-weight diagnostics and existing perspective-level rules; do not silently normalize partial/missing KPI sets.
- Preserve team-specific handling of missing actuals, zero targets, zero actuals and negative values. Invalid new values fail validation; valid existing exceptional policy behavior requires a characterized test, not an arbitrary global replacement.
- Scoring weight and aggregation weight are different. Where Marketing uses original workbook Target Value as an aggregation input weight, preserve that input as separate immutable evidence. A fixed scoring target must not overwrite that raw aggregation weight accidentally.

### 5.5 Precomputed workbook achievement

Some current paths use workbook-precomputed achievement. Define an explicit source policy per KPI and characterize it before editing rules.

- A unchanged legacy basis may preserve its original precomputed behavior through the compatibility adapter.
- For a weight-only change, retain the validated achievement under its unchanged target/direction/policy and recompute contribution using the new weight; raw actual inputs are not required merely to multiply that validated achievement by a different weight.
- If target or direction changes, validate whether achievement can be recomputed using the existing supported engine and available raw inputs.
- If yes, preview and commit use that engine consistently and preserve workbook achievement as source evidence only.
- If not, block the edit/apply path with an explanation and request the missing raw inputs or a later approved formula adapter. Never present a successful setting change that has no effect.
- Switching achievement sources is visible, previewed and approved; it is not hidden inside a target update.

### 5.6 Deterministic resolution

For new calculations:

1. Verify action capability and server-confirmed data/scope grants.
2. Resolve stable source team + level + applicable position/person + exact reporting month.
3. Find its single approved configuration binding.
4. Resolve the target using its explicit mode and validated unit.
5. Pin configuration and input revisions before computation. Preview/commit/job retries use the same basis.
6. Missing/ambiguous bindings fail closed for scopes that have opted into versioned evaluation.

For historical reads:

1. Use the record/calculation's pinned version and applied KPI evidence.
2. Never substitute the latest month/current file settings for that basis.
3. Unmigrated records use a clearly marked, read-only legacy adapter. Do not fabricate an “approved historical version” from today's file.

A legacy fallback remains available only for explicitly unmigrated scopes. The resolver must not silently fall back after a versioned scope's configuration is missing or corrupt.

## 6. Lifecycle, approval and historical protection

```text
Draft -> Validated -> Previewed -> Approved immutable rules
                                      |
                       New upload or explicit Apply job
                                      |
                 Staged results -> Verified -> Activated revision
```

- “Approved rules” and “Applied to existing data” are separate UI states.
- Copy previous month creates a new draft retaining its source version reference; it does not alter the source.
- Draft edits use optimistic concurrency (ETag/revision). Conflicting edits return 409, not last-write-wins.
- Preview records configuration hash, input revision, authorized scope and engine fingerprint. Approval/apply rejects stale previews after rules or input changes.
- Approving replacement rules requires a reason. Old versions remain readable; existing records remain pinned to them.
- A period with rows scored under more than one basis is explicitly flagged. Do not show it as uniform without verification. Initial policy is to require an all-affected-row apply before activating replacement results for a populated scope/month.
- Retrospective correction uses an explicit privileged job, bounded scope, preview and approval. No automatic whole-company history rebuild.
- Stage results and promote atomically; users never see partially updated employee totals with old KPI rows. New uploads and recalculation of the same scope/month must coordinate through a lock/revision check.
- Large jobs are batched; retries are idempotent. Failures preserve the previous active revision and expose progress/errors without leaking unauthorized identities.
- Saved reports retain their historical data/basis snapshots. Regenerated reports get a new revision and basis metadata.
- Existing notes/actions/plans retain their original content and linkage. New derived recommendations may use the activated revision, but do not silently edit human-entered decisions.

## 7. Permissions and RLS contract

Evaluation configuration management is a separate capability from viewing a team or accessing Administration. Default deny and validate authorization on every endpoint/job, not just the navigation UI. [OWASP authorization guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)

| Role | View applied rules/evidence | Prepare drafts/preview | Approve/apply | Administration access |
|---|---|---|---|---|
| Admin | Full authorized system scope | Yes | Yes | Existing access |
| Performance Team | Existing full operational scope | No | No | Remains unavailable |
| Branch Director | Own branch records/team evidence | No | No | No |
| Function Director | Assigned function(s), child teams and authorized branches | No | No | No |
| Regional Manager | Own region only | No | No | No |
| Manager | Existing assigned team and performance-level grants | No | No | No |
| Employee | Own applied scorecard evidence only | No | No | No |
| Legacy roles | Preserve current grant behavior | No new capability automatically | No | Preserve existing restrictions |

Evaluation-management operations are Admin-only under D001. Ordinary applied-result reads reuse the existing team, level, person, branch, function and region authorization contract; management catalog/version access must not be confused with ordinary evidence viewing. Do not implement a parallel authorization framework.

- Non-admin viewers receive only metadata relevant to authorized evidence, not previews of other employees or wider branch/function targets.
- Locked branch/function/region filters stay locked; clear/reset never clears enforced grants.
- Bulk child-team operations authorize every item and reject an unauthorized mixed batch atomically.
- Recheck approval and queued-apply authorization when the job executes; revoked grants cannot survive merely because a preview/job was created earlier.
- Preserve narrow legacy Pre-Approvals grants rather than translating them into broad RCM access.
- No claim of native PostgreSQL RLS completeness is made by this feature; existing server data filtering plus any actual DB RLS must be audited and tested.

## 8. Evaluation Settings UX

Replace the existing KPI Configuration section with **Evaluation Settings**; preserve unrelated Administration sections.

### Main workspace

1. Reporting month/year selector.
2. Function -> team/source sub-team -> performance level -> position/person scope selectors, populated from the live catalog.
3. Readiness, status, version, target-source policy and active-result revision summary.
4. Actions: Copy previous month, Revise this month, Save draft, Validate, Preview impact, Approve; Apply to existing data is a separate guarded action. Revise this month copies the selected month's approved settings into a new version; it does not edit the immutable approved version.
5. Three tabs: **Rules**, **Impact preview**, **History**.

Rules table columns: KPI, unit, target mode, target value, weight %, direction, previous-month value and validation state. Technical formula/aggregation/perspective/source mappings are read-only reference details in release one.

### Clear interaction rules

- Show “No configured period,” “Legacy basis,” “Approved—not yet applied,” “Applied,” “Mixed basis” and “Missing source mapping” distinctly.
- Show weight total and individual errors, with no silent renormalization.
- Different per-person workbook targets appear as “Varies by source row,” not a fabricated single/latest target.
- Copy/bulk edit previews enumerate affected source teams/positions; unsupported scopes cannot disappear silently.
- Impact preview includes changed rules, affected record counts, score/grade/risk differences and source conflicts, with authorized drilldown only.
- When no performance data exists for a month, configuration can be validated and approved, but the UI explicitly says no score impact preview is available yet.
- Historical versions are read-only. “Create revision” is separate from editing a draft.
- Mobile uses labeled editable KPI rows/cards; tablet/desktop use the compact table. Retain keyboard navigation, labels, visible focus, dialog focus trapping and usable touch targets.
- Use static status indicators; no animation-dependent result loading.

Performance Team does not receive an Evaluation workspace under D001. Personal `/account` settings stay separate from Administration and monthly evaluation management.

## 9. Downstream integration and acceptance matrix

| Consumer | What must update when a new result revision is activated | What must remain unchanged |
|---|---|---|
| Upload preview/commit | Targets, weights, direction, conflicts and correct scored output | Same engine/basis between dry run and commit; preserved raw workbook evidence |
| Team dashboard/KPI tiles | Target, achievement, contribution, average, grades and roster ordering | Authorized source scope and existing team aggregation policy |
| Employee profile/360 | Applied monthly KPI evidence, score, grade and comparisons | Other periods and unrelated employees |
| Managerial/Corporate BSC | KPI/perspective weights, coverage, contributions and score using its pinned scope | Existing level/person distinctions and BSC policy |
| Function Summary | Team/role leaderboard, drivers, KPI rollup, roster and trend data | Source identity, child deduplication and authorized population |
| Executive Summary | Company/function/region/level cards, team risks and below-target roster | Existing corporate aggregation policy; score target 100% remains distinct from KPI targets |
| Risk flags | Recomputed grade C/D/E/decline flags and basis-change annotation | No assertion that a scoring-basis change is purely employee performance deterioration |
| Insights/root cause | Direction-aware gaps, lost contributions, comparisons and new recommendations | Preserved historical generated/human-authored decisions |
| Reports/exports | Current regenerated data reflects active revision; include basis/period metadata | Existing saved artifacts remain immutable snapshots |
| Planning | Linked performance evidence/current measured progress can refresh explicitly | Planned targets, baselines, owners and commitments are not overwritten |
| Corrective Actions | New evidence links/suggestions use active basis | Existing action text, status, due date, owner and history |
| Search/navigation | Authorized score snippets update; all drilldowns retain correct month/team scope | No new access to restricted pages/people |
| Caches/pagination | Invalidate/reset affected queries and roster page caches using data + config + scope identity | No cross-user/scope cache reuse; no unnecessary request per row |

For every row above, create an integration test or documented intentional no-change assertion. A settings save test alone cannot satisfy the release.

### Comparisons and heterogeneous settings

- Separate actual operational change from evaluation-score change. Display “Evaluation settings changed” when target, weight, direction, KPI set or policy basis differs.
- Preserve each month's approved basis in trends. Do not silently rescore July using August's target.
- Where selected records have different applied weights/targets, group by compatible basis and expose variation. Do not average weights into a fictional rule.
- Preserve the existing characterized function/company rollup semantics. Any requested normalized “same rules” comparison is a labeled what-if preview, never a replacement for official history.

## 10. API, caching and performance plan

Proposed contracts below are implementation targets, not existing endpoints:

| Endpoint family | Responsibility |
|---|---|
| `GET /api/evaluation/catalog` | Paginated authorized live scopes/readiness; filters for function/team/level |
| `GET /api/evaluation/configurations?scope_id=...&period=YYYY-MM` | Exact-month status/version summary |
| `POST /api/evaluation/drafts` / `PATCH /drafts/{id}` | Create/copy/edit draft with expected revision |
| `POST /drafts/{id}/validate` / `/preview` | Validation and same-engine no-write impact preview |
| `POST /drafts/{id}/approve` | Immutable publish; expected hash and input/preview freshness checks |
| `GET /configurations/{id}` / `/history` | Immutable rules, audit and applied-state metadata |
| `POST /configurations/{id}/apply` | Authorized idempotent job for a bounded existing-data scope |
| `GET /jobs/{id}` | Authorized status and result revision/progress |
| Read DTO extension | `configuration_version_id`, `calculation_revision_id`, basis hash, applied definition/source metadata and comparison warning |

- Use existing authentication, job infrastructure, response/error conventions and permission middleware.
- Stable scope IDs are resolved server-side; the client cannot choose a more permissive identity.
- Validate request allowlists: no edit to policy, SQL, raw formula code, permissions or arbitrary model fields.
- Compatibility GET weights/targets/config routes may remain for old clients, but must not be used as the monthly scoring source. Retire duplicate mutation routes/paths once versioned scopes migrate.
- Resolve all required configurations in bounded bulk queries and memoize per request by full scope/period/version. Avoid N+1 configuration queries per employee/KPI.
- Cache immutable version data by ID/hash. Cache effective bindings by scope+period+config revision; cache results by scope grants+filters+data/calculation revision.
- Replace team-only/infinite current-config frontend caching for effective business settings. Retain long-lived caching only for immutable version payloads.
- Commit rules/results first, then publish durable version/invalidation events. Use retryable post-commit delivery; a Redis outage must not permit stale indefinite client data or roll back an already committed result without evidence.
- Publishing invalidates rule/preview caches; activating results bumps data/calculation revisions and invalidates all dependent dashboards, BSC, insights, report previews and employee-page caches.
- Cancel stale client requests; reject responses from an old user/scope/period. Notify an open page that results changed and refresh/reset paging safely.
- Measure baseline and post-change upload time, dashboard p50/p95, query count and cache hit rate. Agree numeric budgets from measurements rather than invented guarantees.

## 11. Phased implementation roadmap

No implementation phase is complete until its exit gate has evidence. The whole initial release requires Phases 0–8; a read-only UI, schema-only migration or one-team pilot is not full delivery.

| Phase | Goal | Depends on | Release status |
|---|---|---|---|
| 0 | Runtime inventory and golden baselines | Business approval of defaults | Audit only |
| 1 | Version/provenance data foundation | 0 | Behind flag |
| 2 | Central resolver and engine adapters | 1 | Shadow mode |
| 3 | Draft/validation/preview/approval API and permissions | 2 | Internal use |
| 4 | Upload and applied evidence integration | 2–3 | Pilot data only |
| 5 | All downstream consumer/cache integration | 4 | Pilot verification |
| 6 | Responsive Evaluation Settings workflow | 3, 5 for end-to-end acceptance | UAT |
| 7 | Controlled recalculation/history migration | 4–6 | Explicit gated apply |
| 8 | All-team UAT, rollout and live verification | 0–7 | Initial production release |
| 9 | Safe formula expansion | 8 + actual formula examples | Separate future release |

### Phase 0 — Inventory, decisions and characterization

**Work:** Reconcile DB teams, file templates, level/position/person scopes, importers, legacy defaults, merged groups, policy/aggregation variants, grade sources and cache/read paths. Inspect real version schema and existing data. Build a coverage register for every live scope. Collect anonymized July/August workbook examples and official expected results. Confirm target-source and authority defaults.

**Deliverables:** Scope coverage register; source-to-calculation-to-consumer dependency map; golden fixtures; schema-gap report; agreed business decision log and performance baseline.

**Exit gate:** Every live scope is classified and every scoring path has an owner/test. History recoverability is known; ambiguous targets/configurations are listed rather than guessed.

### Phase 1 — Schema and immutable evidence

**Work:** Reuse/repair version groundwork; add required ORM mappings, monthly bindings, provenance and audit/revision support. Account for management history and partitioned employee record identity. Add constraints/indexes and safe legacy-null behavior.

**Deliverables:** Expand-only migration(s), upgrade/rollback runbook, repositories/typed contracts and staging schema tests.

**Exit gate:** Fresh and existing database upgrades succeed, old app compatibility is demonstrated, no historical result changes, duplicate/overlap publication is rejected under concurrency. Rollback after real use preserves referenced evidence; destructive downgrade is not a routine production rollback.

### Phase 2 — Effective resolver and scoring adapters

**Work:** Create deterministic period/scope resolution, legacy adapter, target-source normalization and pinned configuration DTO. Route all policy families through it without changing their characterized formula/aggregation/cap semantics. Handle precomputed achievements and management records explicitly.

**Deliverables:** Resolver contract, adapter registry and golden/unit tests across every scope family.

**Exit gate:** Same basis + inputs yields same result; future/current settings cannot alter historical reads; unsupported edits fail visibly; July 55% and August 65% resolve independently.

### Phase 3 — API workflow and authorization

**Work:** Admin-only draft/copy/edit/validate/preview/approve/history endpoints; optimistic concurrency; preview freshness; audit reasons; capability mapping. Performance Team does not manage evaluation drafts or previews under D001.

**Deliverables:** OpenAPI contracts, error taxonomy, permission matrix and integration tests.

**Exit gate:** Unauthorized direct IDs/bulk batches/previews are denied, revoked grants are rechecked, duplicate approvals cannot create conflicting active bindings, no mutation through deprecated/unversioned routes.

### Phase 4 — Actual upload and persistence integration

**Work:** Use the resolver in synchronous and queued ingestion, dry runs, source-column validation, calculation, root-cause evidence and relational/payload persistence. Pin approved versions and input revisions before scoring; process mixed-team/mixed-period files by their actual scopes.

**Deliverables:** Upload conflict report, applied-basis persistence, job pinning/idempotency and every-family upload fixtures.

**Exit gate:** Saving/approving settings changes real subsequent calculations; preview equals commit; workbook precomputed fields cannot bypass edits; row evidence and total score agree; failures do not commit partial affected data.

### Phase 5 — Consumer integration and cache correctness

**Work:** Update shared read services and every matrix consumer. Stop new pinned evidence being overridden by current config. Adapt merged parent/function views to source-aware definitions. Add basis-change comparisons and separate scoring targets from aggregation input weights. Coordinate backend/frontend invalidation.

**Deliverables:** Extended read DTOs; migrated hooks/aggregators; matrix integration tests; cross-view reconciliation and query/performance measurements.

**Exit gate:** One activated revision is consistent across team, employee, BSC, function, executive, insights and regenerated reports/exports. Historical saved artifacts/plans/actions remain unchanged. Open sessions see updated authorized results without cross-scope leakage or stale pagination.

### Phase 6 — Settings redesign and integrated UAT

**Work:** Replace KPIConfigPanel workflow with live scope selectors, monthly drafts, Rules/Impact/History tabs, copy, totals, source conflicts and separated approve/apply controls. Add responsive/keyboard/error/loading states. Keep Account and admin security settings separate.

**Deliverables:** Complete frontend workflow, typed API hooks, component tests and browser scenarios.

**Exit gate:** Admin completes July-to-August change with no code edit; authorized Performance Team draft flow works if enabled; directors only see permitted applied evidence. 320/375/640/746/768/1024/desktop widths and keyboard use pass without hidden controls or overflow.

### Phase 7 — Recalculation and legacy-history migration

**Work:** Build bounded no-write preview -> approved apply jobs -> staged revisions -> atomic activation. Freeze legacy evidence using recoverable workbook/applied values; do not invent lost historical direction/formulas. Reuse existing version/history facilities where safe. Handle concurrent uploads, cancellations, retries and failed activation.

**Deliverables:** Correction/rollback playbook, migration readiness register, before/after reconciliation, active-revision safety tests.

**Exit gate:** A scoped target correction updates all intended active results without affecting other periods/teams. Prior results/basis remain inspectable. Data insufficiency blocks recalculation visibly. Failure/rollback restores the previous active revision, not guessed recalculated history.

### Phase 8 — Release, all-team coverage and monitoring

**Work:** Run full frontend/backend/migration/permission/integration suites; shadow-check before enabling writes; pilot attendance July/August and a lower-is-better team; then position-based Marketing, Pre-Approvals families and management BSC. Expand only after the coverage register passes. Verify frontend/backend schema/version alignment, queues, caches and live authorized evidence.

**Deliverables:** Signed UAT matrix, backups/migration evidence, release checklist, deployed revision evidence, monitoring and operational guide.

**Exit gate:** Every applicable live team/scope passes its complete workflow or remains explicitly blocked and outside the declared rollout. No silent unsupported team, no cross-scope access regression, no unapproved history change. Post-release checks confirm actual data/basis changes, not merely a READY deployment.

### Phase 9 — Deferred formula configuration

Collect actual old/new formulas and classify reusable policies. Add only reviewed formula families or a restricted expression interpreter with allowlisted operations, bounded complexity and no code execution. Version formulas exactly like other settings. Reuse all history, preview, approval, integration and rollout gates; do not bypass them for a special team.

## 12. Verification scenarios and quality gates

| ID | Scenario | Expected evidence |
|---|---|---|
| EVAL-01 | Copy July 55% target to August and change to 65% | New draft/version; July untouched; August upload uses 65% |
| EVAL-02 | Higher-better sample actual 60%, supported ratio policy capped at 100% | July 100% achievement; August approximately 92.3077% before documented persistence/display rounding |
| EVAL-03 | Change lower-better target and direction separately | Correct preview contributions/colors/arrows under the supported policy; old basis unchanged |
| EVAL-04 | Weight totals 90%, 110%, negatives or invalid decimals | Approval blocked; no silent normalization; valid zero diagnostics treated according to policy |
| EVAL-05 | Workbook/fixed-target conflict and precomputed achievement | Visible conflict/source decision; no silent bypass; preview equals commit |
| EVAL-06 | Different workbook targets for people in the same position | Applied row targets preserved; editor displays source variation |
| EVAL-07 | Every catalog scope and newly onboarded team | Resolver + upload + persistence + all applicable consumers pass; unsupported mapping visibly blocked |
| EVAL-08 | Marketing positions/period variant and target-derived aggregation input | Original technical aggregation preserved; edited scoring target does not overwrite aggregation weights |
| EVAL-09 | Merged Pre-Approvals/RCM parent | Child basis retained, employee deduplication correct, narrow legacy grants not widened |
| EVAL-10 | Managerial/Corporate BSC, positions and person-specific configuration | Correct monthly settings and perspectives; no mixing with Employee scope |
| EVAL-11 | Changed rules after a preview / concurrent approval / job retry | Stale operation rejected or same pinned basis used; no duplicate/partial activation |
| EVAL-12 | Publish for a populated month | Existing rows remain unchanged until explicit apply; state/basis differences clearly visible |
| EVAL-13 | Controlled historical correction and rollback | Bounded records revised; previous revision recoverable; other teams/months unchanged |
| EVAL-14 | Direct unauthorized scope/version/job/export and grant revocation | Denial in API and worker; no identity/count leak through preview or cache |
| EVAL-15 | Redis unavailable or reconnect; already-open browser | Durable invalidation/revision identity prevents indefinite stale or cross-scope results |
| EVAL-16 | Saved report, human-entered plan and corrective action | Original snapshot/text/targets/status unchanged; regenerated evidence explicitly versioned |
| EVAL-17 | Mobile/tablet/desktop, dark theme and keyboard | Labeled fields, visible actions/errors/focus, no clipping/overflow; locked filters preserved |
| EVAL-18 | Multi-year January/December, missing month, deactivated team | No latest/future fallback or year collision; historical identity retained |
| EVAL-19 | Large team/bulk preview/job | Bounded memory/queries, usable progress, idempotent retry; measured latency within agreed budgets |
| EVAL-20 | Database upgrade/rollback and schema mismatch | Data preserved, service refuses incomplete schema clearly; no runtime UndefinedColumn failure after release |
| EVAL-21 | Revise targets/weights after the selected month is already approved | New draft copied from that month; original approval retained; stale preview rejected; explicit apply updates only the selected scope/month; rollback never overwrites newer uploads |

Tests use authorized Local/Test/Staging data; no destructive or password/user/grant-mutating tests in Production. Include real PostgreSQL migration/concurrency/partition coverage, not SQLite-only assertions. Capture numeric reconciliation at storage precision separately from display rounding.

## 13. Rollout, rollback and operating procedure

### Rollout controls

Recommended independent controls for shadow resolver, settings writes and per-scope versioned scoring. Once a scope has versioned records, disabling settings writes must not disable the pinned historical reader. Do not fall back to legacy scoring for those records.

1. Backup and validate recovery in staging.
2. Apply expand-only schema changes; verify runtime/ORM compatibility.
3. Deploy read/resolver compatibility and run shadow comparisons.
4. Enable draft/preview workflow internally.
5. Approve and apply pilot configurations with operator sign-off.
6. Pass the all-team coverage matrix before expanding writes/scoring.
7. Publish operator guide and record frontend/backend/config/data revisions.
8. Monitor resolver failures, source conflicts, mixed bases, job failures, read mismatches, cache lag, scope denials and latency.

### Rollback

- Stop new approvals/apply jobs first; preserve ongoing job evidence.
- Restore previous active configuration/result pointers only through the documented atomic procedure.
- Keep published versions and historical applied evidence; do not drop referenced tables/columns as an emergency rollback.
- Deploy an app version able to read the new provenance. An older app that reinterprets it with current files is not a safe rollback.
- Verify all dependent caches and views after rollback.

### Monthly operator workflow

Select next month -> check coverage -> copy approved prior rules -> edit target/weight/direction -> resolve workbook-source conflicts -> validate -> preview -> Admin approve -> upload/apply -> reconcile views -> close period operationally.

If a month has no new changes, still explicitly approve its copied binding. If historical source evidence is insufficient, leave that scope in labeled legacy mode and resolve the gap before recalculation.

## 14. Risks and decisions to close

| Risk/decision | Mitigation or required decision |
|---|---|
| Existing version tables differ from ORM/runtime | Phase 0 schema audit; reuse/repair one version system |
| Historical rules cannot be recovered | Preserve original applied results; mark uncertain provenance; never backfill today's rules as historical fact |
| Precomputed achievements ignore new target/direction | Explicit source policy and same-engine preview; block unsupported recomputation |
| Target is also an aggregation input | Separate raw aggregation weight from edited scoring target |
| Mixed-basis monthly data | Pin every row; show warning; controlled whole-affected-scope activation |
| Future rule alters old direction/labels | Immutable basis; no current-definition override on pinned reads |
| Performance Team accidentally receives evaluation-management rights | Enforce D001 Admin-only on every endpoint/job before any catalog write; ordinary authorized result reads remain available |
| Scope nulls/overlaps allow duplicate publication | Normalize scope identity and database constraints + concurrency tests |
| Correction job loses notes/actions/report history | Version calculation data only; preserve human artifacts and explicit links |
| Redis failure leaves stale browser data | Durable post-commit delivery, revision keys and bounded refresh/fallback |
| New team appears without an adapter | Dynamic coverage/readiness register; fail visibly; onboarding gate |

D001–D005 above settle management authority, unsupported formula behavior, fixed-target conflicts, August Outbound Productivity and explicit post-approval monthly corrections. Remaining decisions before any wider activation include distinct branch scoring overrides and operational period locks. Do not silently introduce these features.

## 15. Overall definition of done and next implementation step

- [ ] Business defaults approved and all real team/scope inventory reconciled.
- [ ] Version data foundation is proven on existing PostgreSQL data.
- [ ] All supported scoring paths use the same period-aware resolver contract.
- [ ] Target/weight/direction edits affect actual subsequent calculations, not only UI values.
- [ ] Applied KPI evidence, version links and result revisions are persisted consistently.
- [ ] Every downstream matrix row has passing evidence or a documented intentional no-change rule.
- [ ] Historical periods, notes/actions/plans and saved report artifacts remain protected.
- [ ] Permissions, locked filters and cache scope isolation pass tampering/revocation tests.
- [ ] Every applicable real team/position/level and new-team onboarding is covered.
- [ ] Responsive UX, performance budgets, failure/retry behavior and rollback pass.
- [ ] Live post-deployment verification confirms authorized real data and the deployed basis.

**Next step:** Close the independently reproduced permission, scoring-completeness, Outbound source-basis, immutable-history, stale-rollback and frontend gate findings; reconcile one forward migration chain; then run integrated verification before a reviewed local merge. Publishing main or deploying is a separate step, requiring the release and recovery gates above. Phase 9 remains out of scope.

## 16. Reference maintenance

Admin operating guidance is maintained in [the monthly evaluation guide](../guides/monthly-evaluation-admin.md). Its candidate status must remain explicit until integrated and release gates pass.

Update this document after each implementation phase with changed files, decisions, migrations, test evidence, remaining scope gaps and active rollout status. Mark a phase complete only when its exit gate is met. Keep proposals distinguishable from deployed behavior. The root `task_plan.md`, `findings.md` and `progress.md` hold session tracking; this file is the durable implementation reference.
