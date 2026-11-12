# PMS Phase 2 coverage manifest

Version `2.1.0` from repository sources at baseline `fabbb3d461c044bd367e6cc38a9c514fcfe300d2`.
Input fingerprint `62a43d291ba9f60160e907d677dcd2e6b116b2191d1a83a3ab03a530d23ba66b`.

This is the domain/data map for Plan Phase 2. The governing write-up is `docs/plans/pms-ai-evidence-first/`. Capability claims in that write-up are not copied here. The runtime registries `Backend/services/ai/catalog.py` and `Backend/services/ai/coverage_manifest.py` use the same roadmap vocabulary (Phase 2, issue #94); `CERTIFIED` is never emitted.

No cell is verified. Verified would require a passing source-parity check and a passing permission check. Permission checks were not executed. Published performance rows were not read. AI is not enabled. The file has no employee names, identifiers, emails, or scores.

Status words are only: verified, verified no data, partial, blocked, not applicable. `partial` here means one repository parity check passed. `blocked` with `status_basis` `not_checked` means the check was not run.

## Vocabulary mapping (Backend follow-up, not applied in runtime)

### catalog.py

- `verified` → verified. Only when evidence_ref cites an independent source-parity check and a permission check. A catalog row marked verified because every static gate is true is not this state.
- `partial_evidence` → partial. Legacy word, no longer emitted. Synthetic or application tests exist and independent source parity is still open. That is not the same event as a team JSON matching kpi_service.DEFAULT_WEIGHTS.
- `unverified` → blocked. Legacy word, no longer emitted. The roadmap set has no unverified member. An unchecked scope is blocked from certification. status_basis not_checked means no check failed.
- `unsupported` → not applicable. Legacy word, no longer emitted. The operation does not apply. Use blocked when a source contradiction or a missing permission stops an operation that does apply.

### coverage_manifest.py

- `CERTIFIED` → None. Refused. A snapshot row count is not source parity plus permission. The runtime never emits CERTIFIED as capability truth.
- `PENDING` → blocked. Legacy word, no emitter. status_basis not_checked. Not partial.
- `VERIFIED_NO_DATA` → verified no data. Legacy word, no emitter. Only after the scope and calculation are verified and the requested period is confirmed empty. A level existing with a snapshot count of 0, without a permission check, is blocked, not verified no data.
- `NOT_APPLICABLE` → not applicable. Legacy word, no emitter. Same meaning when the operation or level does not apply.
- `BLOCKED_SOURCE` → blocked. Legacy word, no emitter. Same meaning when a source contradiction stops the cell.

## Disagreements with the governing docs

- none

## Corrective-action pilot cells

70 scorecard scopes. Plan: `docs/plans/PMS_AI_EVIDENCE_FIRST_IMPLEMENTATION_PLAN.md#First product pilot`.

- kpi_actual: blocked 70
- kpi_target: blocked 70
- kpi_direction: partial 69, blocked 1
- prior_corrective_actions: blocked 70

Each selectable scorecard scope the pilot would need. Actual and target numbers are not in the repo. Direction text is partial only when one config source states it and no second basis is waiting. That partial is not catalog partial_evidence. Runtime code is unchanged.

Alias conflicts are filed under `open_questions.unresolved_naming_and_hierarchy`, in the shape of `OPEN_QUESTIONS_AND_EVIDENCE_GAPS.md`. That register was not edited.

## Counts

- Countries: 3 (EGY, UAE, shared)
- Functions: 14 (Administration, CRM, CSR, Call Center, Finance, Human Resources, IT, Marketing, Nursing, PMO, Pharmacy, Pre-Approvals, RCM, Sales)
- Teams: 28
- Positions: 55
- Position/level pairs: 56
- Levels: 3 (Corporate, Employee, Managerial)
- KPIs: 402 (35 not in score)
- Matrix cells: 784

### Matrix cells by status

- verified: 0
- verified no data: 0
- partial: 14
- blocked: 735
- not applicable: 35

## RCM Egypt and RCM UAE

Shared parent: RCM region All.

Egypt teams: Coding EGY, Pre-Approvals IP, Pre-Approvals IP Offshore, Resubmission, Submission EGY.

UAE teams: Coding, Pre-Approvals IP Elective Dubai, Pre-Approvals IP Final Dubai, Pre-Approvals IP Final SHJAJM, Pre-Approvals OP Dubai, Pre-Approvals OP Final SHJAJM, Re-Submission, Submission.

RCM Egypt children and RCM UAE children are separate config teams. The RCM parent region All stays shared. No alias was resolved onto the other country.

## Unresolved alias conflicts

- `action-slug:pre-approvals-ip-final` (distinct_teams_collapsed_by_code) alias `pre-approvals-ip-final` → Pre-Approvals IP Final Dubai (UAE), pre-approvals-ip-final (UAE), pre-approvals-ip-final-shj-ajm (UAE). Action-note slugs for two source teams store notes on one team row. The source teams remain separate in the catalog.
- `action-slug:pre-approvals-op-final` (distinct_teams_collapsed_by_code) alias `pre-approvals-op-final` → Pre-Approvals OP Dubai (UAE), pre-approvals-op-final (UAE), pre-approvals-op-final-shj-ajm (UAE). Action-note slugs for two source teams store notes on one team row. The source teams remain separate in the catalog.
- `collapse:pre-approvals-ip-final` (distinct_teams_collapsed_by_code) alias `Pre-Approvals IP Final` → Pre-Approvals IP Final (UAE), Pre-Approvals IP Final Dubai (UAE), Pre-Approvals IP Final SHJAJM (UAE). canonicalTeamName returns one presentation name for IP Final Dubai and IP Final SHJAJM. Those source teams have separate config files and stay separate in this manifest. Pre-Approvals IP Final has no team JSON.
- `collapse:pre-approvals-ip-offshore` (distinct_teams_collapsed_by_code) alias `Pre-Approvals IP` → Pre-Approvals IP (EGY), Pre-Approvals IP Offshore (EGY). egyptRcmTeamValue returns Pre-Approvals IP for both Pre-Approvals IP and Pre-Approvals IP Offshore. countryTeamIdentity.ts says those Egypt teams are not aliases. Both config files are kept.
- `collapse:pre-approvals-op-final` (distinct_teams_collapsed_by_code) alias `Pre-Approvals OP Final` → Pre-Approvals OP Dubai (UAE), Pre-Approvals OP Final (UAE), Pre-Approvals OP Final SHJAJM (UAE). canonicalTeamName returns one presentation name for OP Dubai and OP Final SHJAJM. Those source teams have separate config files and stay separate in this manifest. Pre-Approvals OP Final has no team JSON.
- `cross-country:coding` (same_display_name_across_countries) alias `Coding` → Coding (UAE), Coding EGY (EGY). Business name Coding is used for both an Egypt source team and a UAE source team. The stored teams stay separate. A bare name without a country is unresolved.
- `cross-country:re-submission` (same_display_name_across_countries) alias `Re-Submission` → Re-Submission (UAE), Re-Submission EGY (EGY), Resubmission (EGY). Business name Re-Submission is used for both an Egypt source team and a UAE source team. The stored teams stay separate. A bare name without a country is unresolved.
- `cross-country:submission` (same_display_name_across_countries) alias `Submission` → Submission (UAE), Submission EGY (EGY). Business name Submission is used for both an Egypt source team and a UAE source team. The stored teams stay separate. A bare name without a country is unresolved.
- `default:rcm-group-uae` (unsafe_default) alias `RCM` → RCM (UAE), RCM (shared). rcmGroupForTeam falls through to UAE when the region text is not Egypt or UAE. The RCM config region is All, so that fallback would label the shared parent as UAE. This manifest keeps the parent shared and does not apply the fallback.
- `default:shared-route-uae` (unsafe_default) alias `Coding|Submission|Re-Submission` → Coding (UAE), Coding EGY (EGY), Re-Submission (UAE), Resubmission (EGY), Submission (UAE), Submission EGY (EGY). countryForSharedRoute defaults a shared business route with no region to UAE. That default is not used to classify teams in this manifest.
- `position-missing:cfo` (alias_target_missing) alias `cfo` → Finance / CFO. The position alias matches a Management BSC catalog position, but that position is not in the team JSON. The two sources were not merged.
- `position-missing:digital marketing manager` (alias_target_missing) alias `digital marketing manager` → Marketing / Digital Marketing Manager. The position alias matches a Management BSC catalog position, but that position is not in the team JSON. The two sources were not merged.
- `position-missing:enterprise project management office manager` (alias_target_missing) alias `enterprise project management office manager` → PMO / Enterprise Project Management Office Manager. The position alias matches a Management BSC catalog position, but that position is not in the team JSON. The two sources were not merged.
- `position-missing:group crm director` (alias_target_missing) alias `group crm director` → CRM / Group CRM Director. The position alias matches a Management BSC catalog position, but that position is not in the team JSON. The two sources were not merged.
- `position-missing:group rcm director` (alias_target_missing) alias `group rcm director` → RCM / Group RCM Director. The position alias matches a Management BSC catalog position, but that position is not in the team JSON. The two sources were not merged.
- `position-missing:pre-authorization senior specialist` (alias_target_missing) alias `pre-authorization senior specialist` → Pre-Approvals IP / Pre-Authorization Senior Specialist. The position alias points at a team or position that is not in a team config file or the Management BSC catalog. It was not remapped.
- `position-missing:sgh uae group nursing director` (alias_target_missing) alias `sgh uae group nursing director` → Nursing / SGH UAE Group Nursing Director. The position alias matches a Management BSC catalog position, but that position is not in the team JSON. The two sources were not merged.
- `position-missing:sgh uae group pharmacy director` (alias_target_missing) alias `sgh uae group pharmacy director` → Pharmacy / SGH UAE Group Pharmacy Director. The position alias matches a Management BSC catalog position, but that position is not in the team JSON. The two sources were not merged.
- `region-switch:coding-submission-resubmission` (region_dependent_resolution) alias `coding | submission | resubmission | re-submission` → Coding (UAE), Coding EGY (EGY), Re-Submission (UAE), Resubmission (EGY), Submission (UAE), Submission EGY (EGY). resolve_canonical_team_name picks Egypt or UAE from a region hint, including a hint parsed from the prompt. This manifest does not call that function and does not pick a side.
- `route-map:administration` (route_display_db_mismatch) alias `administration` → Administration, Offshore Admin & Management. The same route id has different display and database names. Neither was chosen as a new team.
- `route-map:pre-approvals-ip-elective-dubai` (route_display_db_mismatch) alias `pre-approvals-ip-elective-dubai` → Pre-Approvals IP Elective, Pre-Approvals IP Elective Dubai. The same route id has different display and database names. Neither was chosen as a new team.
- `route:pre-approvals` (same_alias_multiple_targets) alias `pre-approvals` → Pre-Approvals, Pre-Approvals IP Offshore. The same alias is attached to more than one team or country in repository tables. No target was chosen.
- `spelling:coding` (mismatched_spellings) alias `coding` → Coding, Coding (UAE), Coding EGY (EGY). These spellings collapse to the same letters-and-digits key but name different targets. Frontend teamRouteKey strips punctuation, so a non-exact lookup can collide. No spelling was chosen.
- `spelling:preapprovalsipelective` (mismatched_spellings) alias `preapprovalsipelective` → Pre-Approvals IP Elective (shared), Pre-Approvals IP Elective Dubai. These spellings collapse to the same letters-and-digits key but name different targets. Frontend teamRouteKey strips punctuation, so a non-exact lookup can collide. No spelling was chosen.
- `spelling:preapprovalsipelectivedubai` (mismatched_spellings) alias `preapprovalsipelectivedubai` → Pre-Approvals IP Elective, Pre-Approvals IP Elective Dubai, Pre-Approvals IP Elective Dubai (UAE). These spellings collapse to the same letters-and-digits key but name different targets. Frontend teamRouteKey strips punctuation, so a non-exact lookup can collide. No spelling was chosen.
- `spelling:preapprovalsipfinal` (mismatched_spellings) alias `preapprovalsipfinal` → Pre-Approvals IP Final, Pre-Approvals IP Final (shared), Pre-Approvals IP Final Dubai. These spellings collapse to the same letters-and-digits key but name different targets. Frontend teamRouteKey strips punctuation, so a non-exact lookup can collide. No spelling was chosen.
- `spelling:preapprovalsipfinalshjajm` (mismatched_spellings) alias `preapprovalsipfinalshjajm` → Pre-Approvals IP Final Dubai, Pre-Approvals IP Final SHJAJM, Pre-Approvals IP Final SHJAJM (UAE). These spellings collapse to the same letters-and-digits key but name different targets. Frontend teamRouteKey strips punctuation, so a non-exact lookup can collide. No spelling was chosen.
- `spelling:preapprovalsopfinal` (mismatched_spellings) alias `preapprovalsopfinal` → Pre-Approvals OP Dubai, Pre-Approvals OP Final, Pre-Approvals OP Final (shared). These spellings collapse to the same letters-and-digits key but name different targets. Frontend teamRouteKey strips punctuation, so a non-exact lookup can collide. No spelling was chosen.
- `spelling:preapprovalsopfinalshjajm` (mismatched_spellings) alias `preapprovalsopfinalshjajm` → Pre-Approvals OP Dubai, Pre-Approvals OP Final SHJAJM, Pre-Approvals OP Final SHJAJM (UAE). These spellings collapse to the same letters-and-digits key but name different targets. Frontend teamRouteKey strips punctuation, so a non-exact lookup can collide. No spelling was chosen.
- `spelling:resubmission` (mismatched_spellings) alias `resubmission` → Re-Submission, Re-Submission (UAE), Re-Submission EGY (EGY), Resubmission (EGY), Resubmission. These spellings collapse to the same letters-and-digits key but name different targets. Frontend teamRouteKey strips punctuation, so a non-exact lookup can collide. No spelling was chosen.
- `spelling:resubmissionegy` (mismatched_spellings) alias `resubmissionegy` → Re-Submission EGY (EGY), Re-Submission EGY, Resubmission (EGY). These spellings collapse to the same letters-and-digits key but name different targets. Frontend teamRouteKey strips punctuation, so a non-exact lookup can collide. No spelling was chosen.
- `spelling:submission` (mismatched_spellings) alias `submission` → Submission, Submission (UAE), Submission EGY (EGY). These spellings collapse to the same letters-and-digits key but name different targets. Frontend teamRouteKey strips punctuation, so a non-exact lookup can collide. No spelling was chosen.
- `team-label:support-positions` (team_label_without_config) alias `Support Positions` → Call Center (EGY), Support Positions (EGY). Position aliases name Support Positions as the team. Those positions are stored on the Call Center config. Support Positions stays a Call Center subteam in the matrix and is not given its own config identity.
- `team:coding` (same_alias_multiple_targets) alias `coding` → Coding (UAE), Coding EGY (EGY). The same alias is attached to more than one team or country in repository tables. No target was chosen.
- `team:re-submission` (same_alias_multiple_targets) alias `re-submission` → Re-Submission (UAE), Re-Submission EGY (EGY), Resubmission (EGY). The same alias is attached to more than one team or country in repository tables. No target was chosen.
- `team:re-submission egy` (same_alias_multiple_targets) alias `Re-Submission EGY` → Re-Submission EGY (EGY), Resubmission (EGY). The same alias is attached to more than one team or country in repository tables. No target was chosen.
- `team:submission` (same_alias_multiple_targets) alias `submission` → Submission (UAE), Submission EGY (EGY). The same alias is attached to more than one team or country in repository tables. No target was chosen.

## Reconciliation

Config entries with no KPIs:

- none

KPIs whose team has no team JSON:

- CRM: 18 catalog KPIs, no team JSON
- Nursing: 15 catalog KPIs, no team JSON
- PMO: 12 catalog KPIs, no team JSON

Corporate catalog region disagrees with team config:

- Finance: config All vs BSC catalog UAE
- RCM: config All vs BSC catalog UAE

Inactive, unsupported, or no-data:

- Pre-Approvals OP Final: unsupported — presentation merge of OP Dubai and OP Final SHJAJM. No KPI config file.
- Pre-Approvals IP Final: unsupported — presentation merge of IP Final Dubai and IP Final SHJAJM. No KPI config file.
- Pre-Approvals IP Elective: unsupported — presentation name beside Pre-Approvals IP Elective Dubai. No KPI config file.
- Pre-Approvals: unsupported — UAE parent route with no team JSON; source teams are the Dubai and SHJAJM configs. No KPI config file.
- Re-Submission EGY: unsupported — route and alias of Resubmission; no separate team JSON. No KPI config file.
- Administration: unsupported — TEAM_NAME_MAP display for route administration; config team is Offshore Admin & Management. No KPI config file.
- Call Center: no-data — team_action_service says the employee-level Call Center row may be inactive in the database after Inbound and Outbound were split. teams.is_active was not read. The config file is present.
- *: no-data — No published month could be derived from repository data. upload_log and performance_records were not read.

Derived names that are not config teams:

- CRM: corporate_bsc_catalog_only (Backend/services/ai/corporate_bsc_catalog_data.py)
- Nursing: corporate_bsc_catalog_only (Backend/services/ai/corporate_bsc_catalog_data.py)
- PMO: corporate_bsc_catalog_only (Backend/services/ai/corporate_bsc_catalog_data.py)

Unexplained active entries: 0.

## Not determined from the repo alone

- Which months are published in performance_records and upload_log.
- Whether each teams.is_active flag is true in the database.
- Whether management_kpi_config rows match corporate_bsc_catalog_data.py.
- Whether stored kpi_values match team JSON keys, weights, direction, and units.
- Whether an authorized role can open each scope (permission checks were not executed).
- Which scoring basis is active for Outbound and Marketing when more than one basis exists.
- Database aggregate published periods. Re-run with --read-db and a repository DATABASE_URL to attach counts only.

The cell-level matrix is in `coverage_matrix.csv`. Each row has its source, ownership, freshness, status reason, and missing evidence.
