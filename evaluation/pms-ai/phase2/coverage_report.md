# PMS Phase 2 coverage manifest

Version `2.1.0` from repository sources at baseline `fabbb3d461c044bd367e6cc38a9c514fcfe300d2`.
Input fingerprint `35efde3746219d67abcfb2b19f2295ae2b0ff57557cdd4ba5b5b1052a204aa8c`.

This is the domain/data map for Plan Phase 2. The governing write-up is `docs/plans/pms-ai-evidence-first/`. Capability claims in that write-up are not copied here. Runtime registries `Backend/services/ai/catalog.py` and `Backend/services/ai/coverage_manifest.py` were not changed.

No cell is verified. Verified would require a passing source-parity check and a passing permission check. Permission checks were not executed. Published performance rows were not read. AI is not enabled. The file has no employee names, identifiers, emails, or scores.

Status words are only: verified, verified no data, partial, blocked, not applicable. `partial` here means one repository parity check passed. It is not catalog `partial_evidence`. `blocked` with `status_basis` `not_checked` means the check was not run.

## Vocabulary mapping (Backend follow-up, not applied in runtime)

### catalog.py

- `verified` → verified. Only when evidence_ref cites an independent source-parity check and a permission check. A catalog row marked verified because every static gate is true is not this state.
- `partial_evidence` → partial. Synthetic or application tests exist and independent source parity is still open. That is not the same event as a team JSON matching kpi_service.DEFAULT_WEIGHTS.
- `unverified` → blocked. The roadmap set has no unverified member. An unchecked scope is blocked from certification. status_basis not_checked means no check failed.
- `unsupported` → not applicable. The operation does not apply. Use blocked when a source contradiction or a missing permission stops an operation that does apply.

### coverage_manifest.py

- `CERTIFIED` → None. Refused. A snapshot row count is not source parity plus permission. Backend must stop emitting CERTIFIED as capability truth.
- `PENDING` → blocked. status_basis not_checked. Not partial.
- `VERIFIED_NO_DATA` → verified no data. Only after the scope and calculation are verified and the requested period is confirmed empty. The current runtime sets this when a level exists and a snapshot count is 0, without a permission check.
- `NOT_APPLICABLE` → not applicable. Same meaning when the operation or level does not apply.
- `BLOCKED_SOURCE` → blocked. Same meaning when a source contradiction stops the cell.

## Disagreements with the governing docs

- `glossary:call-center-is-a-team-file` — doc claim: Call Center is a function, not a team. Repo: Backend/config/teams/call_center.json defines a team named Call Center. The function list also contains Call Center.
- `glossary:inbound-aht-tracking-only` — doc claim: Inbound AHT is a tracking-only indicator. Repo: inbound.json scores AHT at weight 0.05.
- `glossary:performance-level-database-values` — doc claim: Performance level database values are employee and management. Repo: performance_records.performance_level is constrained to Employee, Managerial, and Corporate. teams.team_level is a different column and uses employee and management.
- `glossary:pre-approvals-northern-name` — doc claim: UAE RCM includes Pre-Approvals IP Final Northern (Sharjah & Ajman). Repo: No team JSON uses Northern. The config name is Pre-Approvals IP Final SHJAJM.
- `glossary:resubmission-alias-already-resolved` — doc claim: Resubmission and Re-Submission EGY are confirmed aliases of one Egypt team. Repo: Repository alias tables still list that pair as an unresolved conflict (team:re-submission egy). This map does not pick the doc's resolution.
- `glossary:support-role-names` — doc claim: Support roles: Quality Specialist, Trainer, Workforce Specialist Repo: Call Center JSON positions: Call Center trainer, Inbound Team Leader, Outbound Team Leader, Quality Assurance, Workforce analyst
- `kpi-keys:call-center:Inbound` — doc claim: Section keys for Inbound: booking_rate, attendance_rate, quality_score, aht, abandoned_calls, total_calls, branch_bookings Repo: Team JSON template keys: AHT, Attendance, Booking, Other, Quality. In the doc but not the JSON: abandoned_calls, attendance_rate, booking_rate, branch_bookings, quality_score, total_calls. In the JSON but not the doc: Attendance, Booking, Other, Quality.
- `kpi-keys:call-center:Outbound` — doc claim: Section keys for Outbound: booking_rate, attendance_rate, quality_score, aht, abandoned_calls, total_calls, branch_bookings Repo: Team JSON template keys: Attendance, Booking, Other, Quality. In the doc but not the JSON: abandoned_calls, aht, attendance_rate, booking_rate, branch_bookings, quality_score, total_calls. In the JSON but not the doc: Attendance, Booking, Other, Quality.
- `kpi-keys:egypt-rcm:Coding EGY` — doc claim: Section keys for Coding EGY: productivity_ach, quality_accuracy, tat_compliance, rejection_rate Repo: Team JSON template keys: egy_coding_quality_errors, egy_coding_rejection, egy_coding_tat. In the doc but not the JSON: productivity_ach, quality_accuracy, rejection_rate, tat_compliance. In the JSON but not the doc: egy_coding_quality_errors, egy_coding_rejection, egy_coding_tat.
- `kpi-keys:egypt-rcm:Resubmission` — doc claim: Section keys for Resubmission: productivity_ach, quality_accuracy, tat_compliance, rejection_rate Repo: Team JSON template keys: egy_resubmission_quality_errors, egy_resubmission_rejection, egy_resubmission_tat. In the doc but not the JSON: productivity_ach, quality_accuracy, rejection_rate, tat_compliance. In the JSON but not the doc: egy_resubmission_quality_errors, egy_resubmission_rejection, egy_resubmission_tat.
- `kpi-keys:egypt-rcm:Submission EGY` — doc claim: Section keys for Submission EGY: productivity_ach, quality_accuracy, tat_compliance, rejection_rate Repo: Team JSON template keys: egy_submission_due_date, egy_submission_initial_rejection. In the doc but not the JSON: productivity_ach, quality_accuracy, rejection_rate, tat_compliance. In the JSON but not the doc: egy_submission_due_date, egy_submission_initial_rejection.
- `kpi-keys:uae-rcm:Coding` — doc claim: Section keys for Coding: clean_claim_rate, denial_rate, collection_ratio, resubmission_tat Repo: Team JSON template keys: QualityErrors, Rejection, TAT. In the doc but not the JSON: clean_claim_rate, collection_ratio, denial_rate, resubmission_tat. In the JSON but not the doc: QualityErrors, Rejection, TAT.
- `kpi-keys:uae-rcm:Re-Submission` — doc claim: Section keys for Re-Submission: clean_claim_rate, denial_rate, collection_ratio, resubmission_tat Repo: Team JSON template keys: quality_errors_rate, rejection_rate_after_resubmission, tat. In the doc but not the JSON: clean_claim_rate, collection_ratio, denial_rate, resubmission_tat. In the JSON but not the doc: quality_errors_rate, rejection_rate_after_resubmission, tat.
- `kpi-keys:uae-rcm:Submission` — doc claim: Section keys for Submission: clean_claim_rate, denial_rate, collection_ratio, resubmission_tat Repo: Team JSON template keys: initial_rejection_rate, submission_within_due_date. In the doc but not the JSON: clean_claim_rate, collection_ratio, denial_rate, resubmission_tat. In the JSON but not the doc: initial_rejection_rate, submission_within_due_date.
- `kpi-weight:Inbound:aht` — doc claim: aht weight 0.0 tracking=True Repo: Inbound JSON key AHT weight 0.05
- `matrix:bsc-teams-unnamed` — doc claim: Sections 2.1 and 2.2 do not name these Management BSC catalog teams. Repo: Present only in corporate_bsc_catalog_data.py: CRM, Nursing, PMO
- `matrix:config-teams-absent` — doc claim: The governing matrix does not list every config team. Repo: Config teams with no row in sections 2.1 or 2.2: Call Center, Finance, Human Resources, IT, Offshore Admin & Management, Pre-Approvals IP Elective Dubai, Pre-Approvals IP Final Dubai, Pre-Approvals IP Final SHJAJM, Pre-Approvals IP Offshore, Pre-Approvals OP Dubai, Pre-Approvals OP Final SHJAJM, RCM
- `matrix:names-without-team-json` — doc claim: Matrix team names with no team JSON: Pre-Approvals IP Dubai, Pre-Approvals OP Final Repo: Those names are not Backend/config/teams entries. Support Positions is a Call Center subteam and is not in this list.
- `matrix:status-mismatch` — doc claim: Mapped governing status differs from this inventory. Repo: Inbound score: doc partial_evidence maps to partial; inventory status is blocked (structural_block) ; Inbound actual/target: doc partial_evidence maps to partial; inventory status is blocked (structural_block) ; Inbound ranking: doc partial_evidence maps to partial; inventory status is blocked (not_checked) ; Inbound trend: doc partial_evidence maps to partial; inventory status is blocked (not_checked) ; Inbound comparison: doc partial_evidence maps to partial; inventory status is blocked (not_checked) ; Inbound follow-up: doc partial_evidence maps to partial; inventory status is blocked (structural_block) ; Inbound navigation: doc partial_evidence maps to partial; inventory status is blocked (not_checked) ; Outbound score: doc partial_evidence maps to partial; inventory status is blocked (structural_block) ; Outbound actual/target: doc partial_evidence maps to partial; inventory status is blocked (structural_block) ; Outbound ranking: doc partial_evidence maps to partial; inventory status is blocked (not_checked) ; Outbound trend: doc partial_evidence maps to partial; inventory status is blocked (not_checked) ; Outbound comparison: doc unsupported maps to not applicable; inventory status is blocked (not_checked) ; Outbound follow-up: doc partial_evidence maps to partial; inventory status is blocked (structural_block) ; Outbound navigation: doc partial_evidence maps to partial; inventory status is blocked (not_checked) ; Support Positions score: doc partial_evidence maps to partial; inventory status is blocked (structural_block) ; Support Positions actual/target: doc partial_evidence maps to partial; inventory status is blocked (structural_block) ; Support Positions ranking: doc partial_evidence maps to partial; inventory status is blocked (not_checked) ; Support Positions trend: doc partial_evidence maps to partial; inventory status is blocked (not_checked) ; Support Positions comparison: doc unsupported maps to not applicable; inventory status is blocked (not_checked) ; Support Positions follow-up: doc partial_evidence maps to partial; inventory status is blocked (structural_block) ; Support Positions navigation: doc partial_evidence maps to partial; inventory status is blocked (not_checked) ; Coding EGY score: doc partial_evidence, no inventory cell ; Coding EGY actual/target: doc partial_evidence, no inventory cell ; Coding EGY comparison: doc unsupported, no inventory cell ; Coding EGY navigation: doc partial_evidence, no inventory cell ; Submission EGY score: doc partial_evidence, no inventory cell ; Submission EGY actual/target: doc partial_evidence, no inventory cell ; Submission EGY comparison: doc unsupported, no inventory cell ; Submission EGY navigation: doc partial_evidence, no inventory cell ; Resubmission score: doc partial_evidence, no inventory cell ; Resubmission actual/target: doc partial_evidence, no inventory cell ; Resubmission comparison: doc unsupported, no inventory cell ; Resubmission navigation: doc partial_evidence, no inventory cell ; Pre-Approvals IP score: doc partial_evidence, no inventory cell ; Pre-Approvals IP actual/target: doc partial_evidence, no inventory cell ; Pre-Approvals IP comparison: doc unsupported, no inventory cell ; Pre-Approvals IP navigation: doc partial_evidence, no inventory cell ; Marketing score: doc partial_evidence, no inventory cell ; Marketing comparison: doc unsupported, no inventory cell ; Marketing navigation: doc partial_evidence, no inventory cell ; Coding navigation: doc partial_evidence maps to partial; inventory status is blocked (not_checked) ; Submission navigation: doc partial_evidence maps to partial; inventory status is blocked (not_checked) ; Re-Submission navigation: doc partial_evidence maps to partial; inventory status is blocked (not_checked) ; Pre-Approvals OP Final navigation: doc partial_evidence, no inventory cell ; Pre-Approvals IP Dubai navigation: doc partial_evidence, no inventory cell ; Pharmacy comparison: doc partial_evidence maps to partial; inventory status is blocked (not_checked) ; Pharmacy navigation: doc partial_evidence maps to partial; inventory status is blocked (not_checked) ; CSR navigation: doc partial_evidence maps to partial; inventory status is blocked (not_checked) ; Sales navigation: doc partial_evidence maps to partial; inventory status is blocked (not_checked)
- `matrix:unverified-has-no-roadmap-word` — doc claim: 62 section 2.1/2.2 cells use unverified. Repo: This map does not emit unverified. Unchecked inventory cells use blocked with status_basis not_checked. Cells: Coding EGY Employee ranking; Coding EGY Employee trend; Coding EGY Employee follow-up; Submission EGY Employee ranking; Submission EGY Employee trend; Submission EGY Employee follow-up; Resubmission Employee ranking; Resubmission Employee trend; Resubmission Employee follow-up; Pre-Approvals IP Employee ranking; Pre-Approvals IP Employee trend; Pre-Approvals IP Employee follow-up; Marketing Employee actual/target; Marketing Employee ranking; Marketing Employee trend; Marketing Employee follow-up; Coding Employee score; Coding Employee actual/target; Coding Employee ranking; Coding Employee trend; Coding Employee comparison; Coding Employee follow-up; Submission Employee score; Submission Employee actual/target; Submission Employee ranking; Submission Employee trend; Submission Employee comparison; Submission Employee follow-up; Re-Submission Employee score; Re-Submission Employee actual/target; Re-Submission Employee ranking; Re-Submission Employee trend; Re-Submission Employee comparison; Re-Submission Employee follow-up; Pre-Approvals OP Final Employee score; Pre-Approvals OP Final Employee actual/target; Pre-Approvals OP Final Employee ranking; Pre-Approvals OP Final Employee trend; Pre-Approvals OP Final Employee comparison; Pre-Approvals OP Final Employee follow-up; Pre-Approvals IP Dubai Employee score; Pre-Approvals IP Dubai Employee actual/target; Pre-Approvals IP Dubai Employee ranking; Pre-Approvals IP Dubai Employee trend; Pre-Approvals IP Dubai Employee comparison; Pre-Approvals IP Dubai Employee follow-up; Pharmacy Employee actual/target; Pharmacy Employee ranking; Pharmacy Employee trend; Pharmacy Employee follow-up; CSR Employee score; CSR Employee actual/target; CSR Employee ranking; CSR Employee trend; CSR Employee comparison; CSR Employee follow-up; Sales Employee score; Sales Employee actual/target; Sales Employee ranking; Sales Employee trend; Sales Employee comparison; Sales Employee follow-up
- `relationships:missing-branch-as-zero` — doc claim: A missing value must not be replaced with zero, and a missing branch is also described as zero recorded bookings. Repo: The two sentences disagree. This map does not treat a missing branch as zero.

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
