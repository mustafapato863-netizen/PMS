# KPI Configuration Reference

**Audience:** developers maintaining team configuration, data cleaners, imports, scorecards, dashboards, and reports  
**Last verified:** 2026-08-18  
**Source of truth:** `Backend/config/teams/*.json` plus the scoring services listed in [Source map](#source-map)

This document explains every configured team, performance level, position, KPI weight, calculation method, and target direction. It is intended to be a practical reference for a new developer before changing a KPI or adding a new team.

## 1. How configuration is resolved

1. `load_team_config(team_name)` loads and validates one JSON file from `Backend/config/teams/`.
2. The requested performance level is normalized to `Employee`, `Managerial`, or `Corporate`.
3. `resolve_team_config(config, level, position)` starts with the team configuration, then overlays the selected `performance_levels[level]` block.
4. If the selected level has positions, the position KPI list is overlaid as well. A missing position is an error; the loader does not silently fall back to another position.
5. A top-level `kpis` list is the Employee/default configuration. It is not automatically a Managerial or Corporate configuration. A team has a Managerial or Corporate configuration only when that level is explicitly present.
6. Marketing period variants are selected by the import service using `effective_from` and by matching the complete KPI set for the employee period.
7. The loaded configuration is normalized to the global rule `capping = capped_at_100` and `cap_achievement = true`, including older JSON that used an uncapped flag.

### Configured level coverage

| Team | Configured level(s) | Position scope |
|---|---|---|
| Coding | Employee/default | All positions |
| CSR | Employee/default | All positions |
| Inbound | Employee/default, Managerial, Corporate | Employee/default is legacy operational scoring; Managerial/Corporate are team scorecards |
| Inbound UAE | Employee/default | All positions |
| Marketing | Employee | Media Buyer, Graphic Designer, Social Media Specialist, Account Manager, Web Developer, Content Writer |
| Outbound | Employee/default | All positions |
| Pharmacy | Employee/default | All positions |
| Pre-Approvals IP Elective Dubai | Employee | IP Elective; ER / IP Approval |
| Pre-Approvals IP Final Dubai | Employee | Combined; IP Approval; IP Discharge |
| Pre-Approvals IP Final SHJAJM | Employee | IP Final; SHJ/AJM are branches inside the team |
| Pre-Approvals IP Offshore | Employee/default | All positions |
| Pre-Approvals OP Dubai | Employee | Initial Submission; Final Submission; Calls |
| Pre-Approvals OP Final SHJAJM | Employee | OP Final; SHJ/AJM are branches inside the team |
| Re-Submission | Employee/default | All positions |
| Sales | Employee/default, Managerial, Corporate | Employee/default is operational scoring; Managerial/Corporate are team scorecards |
| Submission | Employee/default | All positions |

## 2. Scoring rules

### 2.1 Standard target-ratio KPIs

Most KPIs use `score_formula` conceptually equal to `target_ratio`, even where the JSON omits that optional field.

| Direction | Formula for achievement | Meaning |
|---|---|---|
| `higher_better` | `actual / target` | More output, completion, quality, revenue, attendance, or coverage is better. |
| `lower_better` | `target / actual` | Less error, rejection, waiting time, delay, cost, deficit, or abandonment is better. |

The achievement is clamped to the range `0.0–1.0` (0–100%). Therefore an actual value better than target earns 100%, not more than 100%.

Edge cases:

- Missing actual or target, or a non-positive target, produces no reliable achievement.
- For a lower-is-better KPI, an actual value of zero is treated as 100% achievement when the target is positive.
- Negative achievement is floored at zero.
- Persisted legacy ratios are used only when raw actual and target values are unavailable; when raw values exist, they are recalculated.

### 2.2 Baseline-80 KPIs

The three Pre-Approvals IP Final Dubai KPIs and the two Pre-Approvals IP Final SHJAJM KPIs use a baseline of 80%:

```text
achievement = max(0, (actual - 0.80) / (target - 0.80))
achievement = clamp(achievement, 0, 1)
```

This makes 80% the starting point: actual performance below 80% receives zero achievement, actual equal to target receives 100%, and performance above target is capped at 100%.

### 2.3 Weighted contribution and final score

For each measured KPI:

```text
contribution_i = capped_achievement_i × weight_i
final_score = min(sum(contribution_i), 1.0) × 100
```

Weights are decimals in JSON and must sum to `1.0` within the loader tolerance. For example, a KPI with weight `0.30` and achievement `0.80` contributes `0.24`, or 24 score points. A KPI cannot contribute more than its configured weight.

### 2.4 Aggregation methods

Aggregation describes how raw values are converted into an actual/target pair before achievement is calculated.

| Method | Calculation | Use it when |
|---|---|---|
| `ratio` | `numerator / denominator` | The source provides counters, such as approved requests divided by assigned requests. The denominator must be positive. |
| `average` | Arithmetic mean of available values | Each row is already a comparable measurement, such as quality score or waiting time. |
| `sum` | Sum of available values | The KPI is a volume or total, such as leads, revenue, queries, or installations. |
| `weighted_average` | `sum(actual × row_weight) / sum(row_weight)`; configured Marketing rollups use `Target Value` as the row weight | A large target volume should have more influence than a small target volume. Non-positive/missing target weights fall back to `1.0` for that row. |
| `rollup: average` | Average of the underlying team/employee KPI measurements | The Managerial and Corporate scorecard KPIs are team-level measures. |

`ratio` is a measurement aggregation, not an achievement calculation. Do not divide an already calculated actual by its target during aggregation; direction-aware scoring does that afterward.

## 3. Team-by-team KPI catalog

Weights below are decimal weights from JSON. `H` means `higher_better`; `L` means `lower_better`. The source expression is shown as `actual / target` or as the configured aggregation.

### 3.1 Coding — [coding.json](../Backend/config/teams/coding.json)

Employee/default configuration; all positions.

| KPI key | Label | Weight | Direction / unit | Actual and target calculation |
|---|---|---:|---|---|
| `QualityErrors` | Quality Errors | 0.20 | L / % | `average` |
| `Rejection` | Rejection | 0.50 | L / % | `average` |
| `TAT` | Turnaround Time | 0.30 | L / hours | `average` |

Why: Coding is primarily controlled by error/rejection prevention and turnaround time. These are loss or delay measures, so lower is better.

### 3.2 CSR — [csr.json](../Backend/config/teams/csr.json)

Employee/default configuration; all positions.

| KPI key | Label | Weight | Direction / unit | Actual and target calculation |
|---|---|---:|---|---|
| `Rejection` | Rejection | 0.40 | L / % | `average` |
| `Queries` | Queries Handled | 0.30 | H / % | `sum` |
| `AttendedCR` | Attended CR | 0.30 | H / count | `average` |

Why: Rejection is a defect outcome, while handled queries and attended contacts measure productive service delivery.

### 3.3 Inbound — [inbound.json](../Backend/config/teams/inbound.json)

#### Employee/default operational KPIs

| KPI key | Label | Weight | Direction / unit | Actual and target calculation |
|---|---|---:|---|---|
| `Attendance` | Attendance Rate | 0.70 | H / % | `A.Attend% / A.Booking%`; target is the configured attendance target |
| `Booking` | Booking Rate | 0.10 | H / % | `A.Booking% / calls.total_handled`; target is the configured booking target |
| `Quality` | Quality Score | 0.05 | H / % | `average` |
| `AHT` | AHT (Handle Time) | 0.05 | L / min | `weighted_average`, weighted by `$calls.total_handled` in the configured aggregation |
| `Other` | Abandon Rate | 0.10 | L / % | `calls.abandoned / calls.total_handled` |

Legacy source note: when the source row contains `A.UTZ%`, the legacy evidence builder presents `Other` as **Utilization**, changes its direction to higher-is-better, and uses the utilization target. The checked-in JSON label is the normal Abandon Rate definition.

#### Managerial level

| KPI key | Label | Weight | Direction / unit | Perspective | Rollup |
|---|---|---:|---|---|---|
| `TeamSLA` | Team SLA | 0.35 | H / % | Internal Process | average |
| `TeamQuality` | Team Quality | 0.30 | H / % | Customer | average |
| `CoachingCompletion` | Coaching Completion | 0.20 | H / % | Learning & Growth | average |
| `AttendanceCompliance` | Attendance Compliance | 0.15 | H / % | Internal Process | average |

#### Corporate level

| KPI key | Label | Weight | Direction / unit | Perspective | Rollup |
|---|---|---:|---|---|---|
| `StrategicDelivery` | Strategic Delivery | 0.35 | H / % | Internal Process | average |
| `GovernanceCompliance` | Governance Compliance | 0.25 | H / % | Internal Process | average |
| `StakeholderSatisfaction` | Stakeholder Satisfaction | 0.25 | H / % | Customer | average |
| `CostEfficiency` | Cost Efficiency | 0.15 | H / % | Financial | average |

Managerial and Corporate enable all four Balanced Scorecard perspectives: Financial, Customer, Internal Process, and Learning & Growth. Their strategy map is `Learning & Growth → Internal Process → Customer → Financial`.

### 3.4 Inbound UAE — [inbound_uae.json](../Backend/config/teams/inbound_uae.json)

Employee/default configuration; all positions.

| KPI key | Label | Weight | Direction / unit | Actual and target calculation |
|---|---|---:|---|---|
| `Attendance` | Attendance Rate | 0.70 | H / % | `A.Attend% / A.Booking%` |
| `Booking` | Booking Rate | 0.20 | H / % | `A.Booking% / calls.total_handled` |
| `Other` | Abandon Rate | 0.10 | L / % | `calls.abandoned / calls.total_handled` |

### 3.5 Marketing — [marketing.json](../Backend/config/teams/marketing.json)

Employee level. KPI sets are position-specific. All rows use `Actual Value` and `Target Value` as the source columns. Unless noted as `sum`, the configured rollup is `weighted_average` by `Target Value`.

#### Media Buyer

| KPI key | Label | Weight | Direction / unit | Perspective | Aggregation |
|---|---|---:|---|---|---|
| `mb_cpl` | CPL | 0.10 | L / AED | Financial | weighted average by Target Value |
| `mb_cr` | CR | 0.30 | H / % | Internal Process | weighted average by Target Value |
| `mb_leads` | Leads | 0.30 | H / count | Customer | sum |
| `mb_cpv` | CPV | 0.10 | L / AED | Financial | weighted average by Target Value |
| `mb_revenue` | Revenue | 0.10 | H / AED | Financial | sum |
| `mb_app_installs` | # App installs | 0.10 | H / count | Customer | sum |

#### Graphic Designer

| KPI key | Label | Weight | Direction / unit | Perspective | Aggregation |
|---|---|---:|---|---|---|
| `gd_on_schedule` | Projects delivered on schedule | 0.40 | H / count | Internal Process | sum |
| `gd_rework` | Rework percentage | 0.25 | L / % | Internal Process | weighted average by Target Value |
| `gd_brand_consistency` | Consistency with brand guidelines | 0.20 | H / % | Internal Process | weighted average by Target Value |
| `gd_edits_rate` | Edits Rate | 0.15 | L / % | Internal Process | weighted average by Target Value |

#### Social Media Specialist

| KPI key | Label | Weight | Direction / unit | Perspective | Aggregation |
|---|---|---:|---|---|---|
| `sms_response_rate` | Response rate (%) | 0.40 | H / % | Customer | weighted average by Target Value |
| `sms_channel_growth` | Channels growth rate | 0.20 | H / % | Customer | weighted average by Target Value |
| `sms_response_time` | Response Time | 0.40 | L / min | Internal Process | weighted average by Target Value |

#### Account Manager — default set

| KPI key | Label | Weight | Direction / unit | Perspective | Aggregation |
|---|---|---:|---|---|---|
| `am_campaign_delivery` | Campaign delivery | 0.15 | H / % | Internal Process | weighted average by Target Value |
| `am_campaign_delivery_ontime` | Campaign delivery Ontime | 0.20 | H / % | Internal Process | weighted average by Target Value |
| `am_deficit` | Deficit | 0.10 | L / % | Financial | weighted average by Target Value |
| `am_requests` | Requests Delivery Rate | 0.10 | H / % | Internal Process | weighted average by Target Value |
| `am_modifications` | Modification Rate | 0.10 | L / % | Internal Process | weighted average by Target Value |
| `am_edit_rate` | Edit Rate | 0.15 | L / % | Internal Process | weighted average by Target Value |
| `am_projects_ontime` | Projects Ontime | 0.20 | H / % | Internal Process | weighted average by Target Value |

#### Account Manager — `may_2026_onward` period variant

Effective from `2026-05-01`; this period variant replaces the default Account Manager set when the period is May 2026 or later.

| KPI key | Label | Weight | Direction / unit | Perspective | Aggregation |
|---|---|---:|---|---|---|
| `am_requests` | Requests delivery | 0.35 | H / % | Internal Process | weighted average by Target Value |
| `am_edit_rate` | Edit Rate | 0.20 | L / % | Internal Process | weighted average by Target Value |
| `am_projects_ontime` | Projects Ontime | 0.45 | H / % | Internal Process | weighted average by Target Value |

#### Web Developer

| KPI key | Label | Weight | Direction / unit | Perspective | Aggregation |
|---|---|---:|---|---|---|
| `wd_uptime` | Website uptime (%) | 0.25 | H / % | Internal Process | weighted average by Target Value |
| `wd_page_speed` | Page load speed | 0.25 | L / sec | Internal Process | weighted average by Target Value |
| `wd_bug_resolution` | Error / bug resolution rate | 0.25 | H / % | Internal Process | weighted average by Target Value |
| `wd_delivery_timeliness` | Request delivery timeliness | 0.25 | H / % | Internal Process | weighted average by Target Value |

#### Content Writer

| KPI key | Label | Weight | Direction / unit | Perspective | Aggregation |
|---|---|---:|---|---|---|
| `cw_organic_traffic` | Organic traffic from content | 0.40 | H / % | Customer | weighted average by Target Value |
| `cw_delivery_timeliness` | Content delivery timeliness | 0.30 | H / % | Internal Process | weighted average by Target Value |
| `cw_error_free` | Error-free content ratio | 0.30 | L / % | Internal Process | weighted average by Target Value |

Configuration caution: `cw_error_free` is currently marked `lower_better` even though its label sounds like a positive quality ratio. Treat the JSON direction as the current contract and verify the intended business meaning before changing it.

Why: Marketing uses volume sums for additive outputs such as leads and revenue. Rate, cost, quality, and timeliness KPIs use target-volume-weighted averages so one small campaign does not have the same influence as a large campaign.

### 3.6 Outbound — [outbound.json](../Backend/config/teams/outbound.json)

Employee/default configuration; all positions.

| KPI key | Label | Weight | Direction / unit | Actual and target calculation |
|---|---|---:|---|---|
| `Attendance` | Attendance Rate | 0.70 | H / % | `A.Attend% / A.Booking%` |
| `Booking` | Booking Rate | 0.10 | H / % | `A.Booking% / calls.total_handled` |
| `Quality` | Quality Score | 0.10 | H / % | `average` |
| `Other` | Reachability | 0.10 | H / % | `average` |

### 3.7 Pharmacy — [pharmacy.json](../Backend/config/teams/pharmacy.json)

Employee/default configuration; all positions.

| KPI key | Label | Weight | Direction / unit | Actual and target calculation |
|---|---|---:|---|---|
| `WaitingTime` | Waiting Time | 0.20 | L / min | `average` |
| `Leakage` | Leakage | 0.20 | L / % | `average` |
| `TenderCompliance` | Tender Compliance | 0.20 | H / % | `average` |
| `ATV` | Average Transaction Value | 0.20 | H / AED | `average` |
| `Prescription` | Prescription Contribution | 0.20 | H / % | `average` |

Why: waiting time and leakage represent delay or loss; compliance, transaction value, and prescription contribution represent positive outcomes.

### 3.8 Pre-Approvals IP Elective Dubai — [pre_approvals_ip_elective_dubai.json](../Backend/config/teams/pre_approvals_ip_elective_dubai.json)

Employee level with two position/workstream KPI sets.

| Position | KPI key | Label | Weight | Direction / unit | Actual and target calculation |
|---|---|---|---:|---|---|
| IP Elective | `ip_initial_rejection_rate` | IP Initial Rejection % | 0.60 | L / % | `RejectedRequests / AssignedRequests` |
| IP Elective | `approval_within_48_hours` | Approval Within 48 Hours % | 0.40 | H / % | `ApprovalWithin48HR / ApprovedRequests` |
| ER / IP Approval | `er_initial_rejection_rate` | ER Initial Rejection % | 0.60 | L / % | `RejectedRequests / AssignedRequests` |
| ER / IP Approval | `approval_within_1_5_hours` | Approval Within 1.5 Hours % | 0.40 | H / % | `ApprovalWithin1.5HR / ApprovedRequests` |

Workstream selection uses the complete source target pair, not one target column in isolation:

- IP Elective: `(initial rejection 3%, turnaround 75%)` or `(6%, 75%)`.
- ER / IP Approval: `(initial rejection 1%, turnaround 100%)` or `(3%, 100%)`.

Missing/unsupported pairs fail ingestion so the system does not guess the workstream. Rows with Status or Performance Grade `Leave`, `New Staff`, or `-` are excluded before scoring. The source ER header says 48 hours, but the canonical KPI is **1.5 hours** and uses `ApprovalWithin1.5HR`.

### 3.9 Pre-Approvals IP Final Dubai — [pre_approvals_ip_final_dubai.json](../Backend/config/teams/pre_approvals_ip_final_dubai.json)

Employee level with three workstream KPI sets. All six configured KPI definitions use the baseline-80 formula.

| Position | KPI key | Label | Weight | Direction / unit | Actual and target calculation |
|---|---|---|---:|---|---|
| Combined | `combined_acceptance_rate` | Acceptance Rate | 0.50 | H / % | `ApprovedRequests / AssignedRequest` |
| Combined | `combined_submission_within_month` | Submission Within Month % | 0.30 | H / % | `SubmittedWithinMonth(Untill3rdofnextmonth) / AssignedRequest` |
| Combined | `combined_discharge_within_one_hour` | Discharge % Within 1 Hour | 0.20 | H / % | `DischargeWithinHour / DischargeRequests` |
| IP Approval | `ip_approval_acceptance_rate` | Acceptance Rate | 0.60 | H / % | `ApprovedRequests / AssignedRequest` |
| IP Approval | `ip_approval_submission_within_month` | Submission Within Month % | 0.40 | H / % | `SubmittedWithinMonth(Untill3rdofnextmonth) / AssignedRequest` |
| IP Discharge | `ip_discharge_within_one_hour` | Discharge % Within 1 Hour | 1.00 | H / % | `DischargeWithinHour / DischargeRequests` |

The source has no Position column. The cleaner reconciles the source Performance Score against the documented weight sets to identify the applied workstream, then recalculates the score. Rows without discharge use the IP Approval 60/40 set; rows without approval use IP Discharge at 100% weight.

### 3.10 Pre-Approvals IP Final SHJAJM — [pre_approvals_ip_final_shj_ajm.json](../Backend/config/teams/pre_approvals_ip_final_shj_ajm.json)

Employee level, IP Final position. SHJ and AJM are branches inside the same scoring team.

| KPI key | Label | Weight | Direction / unit | Actual and target calculation |
|---|---|---:|---|---|
| `ip_final_acceptance_rate` | Acceptance Rate | 0.40 | H / % | `ApprovedRequests / AssignedRequest` |
| `ip_final_submission_within_month` | Submission Within Month % | 0.60 | H / % | `SubmittedWithinMonth(Untill3rdofnextmonth) / AssignedRequest` |

Both KPIs use the baseline-80 formula, floor below-baseline achievement at zero, and cap achievement/final score at 100%.

### 3.11 Pre-Approvals IP Offshore — [pre_approvals_offshore.json](../Backend/config/teams/pre_approvals_offshore.json)

Employee/default configuration; all positions.

| KPI key | Label | Weight | Direction / unit | Actual and target calculation |
|---|---|---:|---|---|
| `Rejection` | Rejection Rate | 0.50 | L / % | `RejectedRequests / AssignedRequest` |
| `InitialError` | Initial Error Rate | 0.20 | L / % | `ErrosClaims / SubmittedClaims` |
| `Submission` | Submission Rate | 0.30 | H / % | `ApprovalWithin48HR / ApprovedRequests` |

The implementation prefers authoritative counters when both numerator and denominator are available; displayed percentage fields are fallback evidence for legacy workbooks.

### 3.12 Pre-Approvals OP Dubai — [pre_approvals_op_dubai.json](../Backend/config/teams/pre_approvals_op_dubai.json)

Employee level with three position/workstream KPI sets.

| Position | KPI key | Label | Weight | Direction / unit | Actual and target calculation |
|---|---|---|---:|---|---|
| Initial Submission | `initial_rejection_rate` | Initial Rejection Rate | 0.60 | L / % | `RejectedRequests / SubmittedRequests` |
| Initial Submission | `submission_within_hour` | Submission Within TAT | 0.40 | H / % | `SubmittedWithinHour / SubmittedRequests` |
| Final Submission | `submission_within_due_date` | Submission Within Due Date | 1.00 | H / % | `SubmittedWithinDay / AssignedRequest` |
| Calls | `abandoned_calls_rate` | Abandoned Calls Rate | 0.60 | L / % | `TotalAbandonedCallsPerDay / TotalNumberOfCallsperDay` |
| Calls | `attended_calls_rate` | Attended Calls Rate | 0.40 | H / % | `TotalAttendedCallsPerDay / TotalNumberOfCallsperDay` |

The workstream is derived from the populated operational volume columns. Final Rejection Rate is intentionally not configured until Final Rejected Requests and its target are supplied.

### 3.13 Pre-Approvals OP Final SHJAJM — [pre_approvals_op_final_shj_ajm.json](../Backend/config/teams/pre_approvals_op_final_shj_ajm.json)

Employee level, OP Final position. SHJ and AJM are branches inside the same scoring team.

| KPI key | Label | Weight | Direction / unit | Actual and target calculation |
|---|---|---:|---|---|
| `initial_rejection_rate` | Initial Rejection % | 0.60 | L / % | `RejectedRequests / SubmittedRequests` |
| `submission_within_tat` | Submission Within TAT % | 0.40 | H / % | `SubmittedWithinHour / SubmittedRequestsExcludingManual` |

Targets and directions are read from each source row. If Submission Within TAT is unavailable, the exception rule uses the Initial Rejection achievement as the final score.

### 3.14 Re-Submission — [re_submission.json](../Backend/config/teams/re_submission.json)

Employee/default configuration; all positions.

| KPI key | Label | Weight | Direction / unit | Actual and target calculation |
|---|---|---:|---|---|
| `quality_errors_rate` | Quality Errors Rate | 0.20 | L / % | `FinalErrorsClaims(RaisedbyQualitySameMonth) / QltySamples` |
| `rejection_rate_after_resubmission` | Rejection Rate After Re-Submission | 0.50 | L / % | `RejectedClaims3MonthsPrevious(byInsurance) / RemittanceAmount` |
| `tat` | TAT | 0.30 | H / % | `TotalSubmittedWithin(TAT) / Allocatedclaims` |

The Re-Submission `tat` value is a **within-TAT completion rate**, not a duration; therefore higher is better.

### 3.15 Sales — [sales.json](../Backend/config/teams/sales.json)

#### Employee/default operational KPIs

| KPI key | Label | Weight | Direction / unit | Actual and target calculation |
|---|---|---:|---|---|
| `OPCensus` | OP Census Ach | 0.10 | H / number | `A.OPCensus / T.OPCensus` |
| `OPRevenue` | OP Revenue Ach | 0.10 | H / currency | `A.OPRevenue / T.OPRevenue` |
| `IPCensus` | IP Census Ach | 0.25 | H / number | `A.IPCensus / T.IPCensus` |
| `IPRevenue` | IP Revenue Ach | 0.45 | H / currency | `A.IPRevenue / T.IPRevenue` |
| `Activity` | Activity Score | 0.10 | H / number | `A.Activity / T.Activity`; activity actual/target are dynamically summed from activity columns |

#### Managerial level

| KPI key | Label | Weight | Direction / unit | Perspective | Rollup |
|---|---|---:|---|---|---|
| `PipelineAttainment` | Pipeline Attainment | 0.35 | H / % | Financial | average |
| `ForecastAccuracy` | Forecast Accuracy | 0.25 | H / % | Internal Process | average |
| `CoachingCompletion` | Coaching Completion | 0.20 | H / % | Learning & Growth | average |
| `EscalationResolution` | Escalation Resolution | 0.20 | H / % | Customer | average |

#### Corporate level

| KPI key | Label | Weight | Direction / unit | Perspective | Rollup |
|---|---|---:|---|---|---|
| `StrategicDelivery` | Strategic Delivery | 0.30 | H / % | Internal Process | average |
| `RevenueGovernance` | Revenue Governance | 0.25 | H / % | Financial | average |
| `StakeholderSatisfaction` | Stakeholder Satisfaction | 0.25 | H / % | Customer | average |
| `ProjectMilestones` | Project Milestone Completion | 0.20 | H / % | Internal Process | average |

Managerial and Corporate enable the same four Balanced Scorecard perspectives and the strategy map `Learning & Growth → Internal Process → Customer → Financial`.

### 3.16 Submission — [submission.json](../Backend/config/teams/submission.json)

Employee/default configuration; all positions.

| KPI key | Label | Weight | Direction / unit | Actual and target calculation |
|---|---|---:|---|---|
| `initial_rejection_rate` | Initial Rejection Rate | 0.60 | L / % | `RejectedClaimsAmount3MonthPrevious / RAClaimsAmount(3MonthPrevious)` |
| `submission_within_due_date` | Submission Within Due Date | 0.40 | H / % | `average` |

## 4. Direction guide for new developers

Choose the direction from the business meaning, not from the numeric shape of the field:

| Ask this question | Use | Examples in this project |
|---|---|---|
| Does a larger value represent more successful output or completion? | `higher_better` | Revenue, leads, attendance, booking, quality, compliance, on-time delivery, approval within TAT |
| Does a larger value represent more defects, delay, loss, cost, or customer pain? | `lower_better` | Rejection, errors, leakage, abandon rate, waiting time, AHT, CPL/CPV, deficit, response time |

Do not invert a KPI merely because it is a percentage. A percentage can be either direction: Approval Within TAT is higher-is-better; Rejection Rate is lower-is-better.

Before adding or changing a KPI, confirm all of the following:

- The key is stable and unique within its resolved level/position.
- The label and source columns match the workbook/import contract.
- The direction is explicit and reflects the desired business outcome.
- The weights sum to `1.0` for every standalone KPI set, including every position and period variant.
- Ratio denominators cannot be zero for valid rows, or the cleaner has an explicit no-data rule.
- The unit and scale are consistent (`0.75` and `75%` must not be mixed without normalization).
- The KPI is capped at 100% and its contribution cannot exceed its weight.
- A level override does not accidentally inherit or mix KPIs from another level.
- A position-scoped KPI has a `perspective` when it participates in Balanced Scorecard reporting.

## 5. Source map

- Configuration loading, validation, level and position resolution: [Backend/config/loader.py](../Backend/config/loader.py)
- Shared aggregation and direction-aware achievement: [Backend/services/kpi_aggregation.py](../Backend/services/kpi_aggregation.py)
- Percent-scale legacy achievement helper: [Backend/data_cleaning/standard_mappings.py](../Backend/data_cleaning/standard_mappings.py)
- Legacy operational KPI evidence and source-counter fallbacks: [Backend/services/legacy_kpi_evidence.py](../Backend/services/legacy_kpi_evidence.py)
- Dashboard read normalization and reconstruction of stale persisted ratios: [Backend/services/dashboard_record_service.py](../Backend/services/dashboard_record_service.py)
- Marketing period-variant selection and KPI-set matching: [Backend/services/marketing_import_service.py](../Backend/services/marketing_import_service.py)
- Balanced Scorecard perspective and rollup calculations: [Backend/services/balanced_scorecard_service.py](../Backend/services/balanced_scorecard_service.py)
- KPI weight/target API projection: [Backend/services/kpi_configuration_service.py](../Backend/services/kpi_configuration_service.py)

When code and this document disagree, treat the checked-in JSON and executable scoring path as authoritative, then update this reference in the same change.
