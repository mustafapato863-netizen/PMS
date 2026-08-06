# Insights 2.0 — Progressive Executive Analysis

## 1. Product Goal

Transform the Insights page from a flat list of underperforming KPIs into a progressive decision-support experience that answers, in order:

1. Where is the performance gap?
2. How large is it?
3. Which geography, function, team, KPI, role, or employee contributes most?
4. Why is the gap happening?
5. Is the issue broad, concentrated, persistent, or data-related?
6. What action is most likely to improve the result?

The page must reveal deeper information only when the user makes a relevant selection. It must not expose every filter, table, and diagnostic at once.

## 2. Product Principles

- **Progressive disclosure:** show only the level of detail needed for the current question.
- **Evidence before narrative:** every insight must be traceable to records, KPI configuration, or trend history.
- **Impact over ranking:** prioritize contribution to the weighted gap, not only the lowest raw score.
- **Direction-aware calculations:** higher-better and lower-better KPIs use different gap logic.
- **Performance is not data quality:** missing actuals, missing targets, low coverage, and invalid configuration are separate issue types.
- **Scope consistency:** all cards, filters, trends, tables, and narratives use the same selected scope.
- **No false causality:** the system may identify contributors and signals, but must not claim a root cause without evidence.
- **Actionability:** every high-priority insight should lead to a clear next action or a documented data/configuration fix.

## 3. Scope and Non-Goals

### In scope

- Executive story for the selected period and organizational scope.
- Geography, team, KPI, population, trend, and data-confidence analysis.
- Cascading filters and progressive drill-down.
- Impact, severity, persistence, spread, concentration, and opportunity metrics.
- Evidence-linked insight cards and prioritized recommendations.
- Consistent calculations across Executive Summary, Team Dashboard, Employee Profile, and Insights.

### Not in scope for the first release

- Autonomous AI decisions or automatic corrective-action creation.
- Unverified causal claims from correlation alone.
- Replacing existing KPI formulas or team-specific scoring rules.
- Rebuilding the database schema before proving that existing historical records are insufficient.
- Showing every employee and every KPI in the executive landing view.

## 4. Information Architecture

### Level 0 — Executive Story

Always visible:

- Period
- Organizational scope (Company, Region, or Country)
- Optional primary function/team scope

Content:

- One executive summary sentence.
- Overall score, target, gap, and period movement.
- Top positive driver.
- Top negative driver.
- Data confidence indicator.
- One primary recommended focus.

### Level 1 — Scope Contribution

Shown after selecting a geography or function scope:

- Geography contribution table or chart.
- Team/function contribution table.
- Current score, target, gap, weighted impact, affected employees, critical KPI count, and persistence.

### Level 2 — Diagnostic Analysis

Shown after selecting a team or KPI:

- KPI drivers ranked by contribution to the selected gap.
- Severity versus business impact.
- Issue type classification.
- Six-period trend and persistence.
- Population spread and concentration.

### Level 3 — Evidence and Action

Shown through a drawer or focused detail view:

- Affected roles and employees.
- Supporting records and periods.
- Data-quality flags.
- Recommended action.
- Expected improvement scenarios.
- Links to Employee Profile, Team Dashboard, KPI detail, or corrective action.

## 5. Filter Strategy

### Always-visible context filters

Keep the top bar limited to three or four controls:

- Period
- Region/Country
- Function/Team
- Optional organizational level

### Contextual diagnostic filters

Reveal only when the selected scope supports them:

- KPI
- Severity
- Issue type
- Trend status
- Above/below target

### Advanced filters drawer

Move low-frequency filters into `More filters`:

- Position
- Manager
- Employee
- Persistence threshold
- Population type
- Data confidence
- Sample-size threshold

### Filter behavior requirements

- Filters must cascade. Selecting a region narrows available teams; selecting a team narrows KPIs and employees.
- Options with no records in the current scope should be hidden or disabled with a clear reason.
- Selecting a drill-down item should update the URL-backed filter state.
- Active filter chips must show the current analytical scope.
- `Reset analysis` returns to Level 0 without clearing the global period unless explicitly requested.
- The page must show a scope summary such as `June 2026 · UAE · RCM · Response Time`.
- Do not render duplicate filters that control the same dimension.
- Multi-select is allowed for regions, teams, and employees where aggregate comparison is meaningful; KPI selection should default to single-select for diagnosis.

## 6. Executive Story Contract

The story is generated from structured facts, not from free-form text alone.

Example structure:

> June performance is 8.4 points below target and declined 2.1 points month over month. UAE contributes 61% of the weighted gap, with RCM and Pre-Approvals contributing most of the decline. Response Time and Initial Rejection are the leading KPI drivers. The recommended focus is the RCM workflow and the seven employees with the largest weighted impact.

Required facts:

- Current score and target.
- Absolute gap in percentage points.
- Period movement.
- Largest geography contribution.
- Largest team contribution.
- Largest KPI contribution.
- Data confidence and any important caveat.
- Recommended focus.

If a required fact cannot be calculated, the story must say `insufficient data` rather than infer a value.

## 7. Calculation Contract

### 7.1 Direction-aware gap

For a higher-better KPI:

`gap = actual - target`

For a lower-better KPI:

`gap = target - actual`

Positive values indicate performance at or above target; negative values indicate a shortfall.

### 7.2 KPI achievement

Use the existing team-specific KPI formula and cap the achievement score according to the product rule. The normalized achievement must be in the range `0–100%` for display and aggregation.

### 7.3 Weighted KPI contribution

For each measured KPI:

`weighted_impact = normalized_gap_magnitude × effective_kpi_weight × coverage_factor`

The UI must expose the inputs or link to evidence. Contributions are normalized within the selected scope so the negative contributors can be expressed as a percentage of the total negative gap.

### 7.4 Geography/team contribution

For each child scope:

`scope_contribution = child_negative_impact / total_negative_impact`

Do not rank only by child score. A lower-scoring small team may contribute less than a larger team with a moderate gap.

### 7.5 Affected employees

Define affected employees as employees with a measured KPI result below the configured target for the selected period. Track separately:

- `affected_count`
- `affected_percentage`
- `high_impact_employee_count`
- `missing_data_count`

### 7.6 Coverage factor

Coverage must not silently reduce or inflate performance. Show:

- Records expected.
- Records measured.
- Coverage percentage.
- Missing actuals.
- Missing targets.

If coverage is below the configured confidence threshold, mark the insight as `partial_data` and reduce its priority confidence.

### 7.7 Opportunity scenarios

For every opportunity, calculate at least three scenarios:

- Minimum improvement.
- Realistic improvement.
- Full target achievement.

Expected lift must respect KPI direction, KPI weight, achievement caps, and the selected population. It is an estimate, not a guarantee.

## 8. Issue Classification

Each insight should have one primary issue type and optional secondary signals:

- `performance_issue`: measured performance is below target.
- `coverage_issue`: too few eligible records are measured.
- `data_quality_issue`: malformed, missing, or inconsistent source values.
- `configuration_issue`: target, weight, direction, or KPI mapping is invalid.
- `volume_issue`: operational volume materially amplifies the business impact.
- `concentration_issue`: most impact comes from a small population.
- `broad_team_issue`: the issue is distributed across most of the selected team.

Issue type must be calculated from explicit thresholds stored in configuration, not hard-coded inside a UI component.

## 9. Trend and Persistence Model

Minimum historical states:

- `new_issue`
- `recurring_issue`
- `worsening`
- `improving_but_below_target`
- `recovered`
- `volatile`
- `stable_at_target`

Rules:

- Use the latest available six periods for the standard trend view.
- Require at least three available periods before labeling an issue persistent.
- Distinguish missing periods from zero performance.
- Compare like-for-like scopes and KPI configurations across periods.
- Flag target or weight changes as a configuration event that may explain movement.

## 10. Priority Model

Each insight receives a transparent priority score based on:

- Weighted business impact.
- Gap severity.
- Number and percentage of affected employees.
- Persistence.
- Rate of decline.
- Business criticality.
- Data confidence.
- Ease of improvement.

Suggested output:

- `P1`: high impact, broad or persistent, actionable.
- `P2`: material impact or fast deterioration, but narrower scope.
- `P3`: limited impact, low confidence, or primarily data/configuration work.

The UI must show the reason for the priority instead of exposing an unexplained number.

## 11. Evidence Contract

Every insight object should contain:

```ts
type InsightEvidence = {
  scope: { period: string; region?: string; team?: string; kpi?: string };
  currentValue?: number;
  targetValue?: number;
  previousValue?: number;
  gap?: number;
  weightedImpact?: number;
  affectedEmployees?: number;
  measuredRecords?: number;
  expectedRecords?: number;
  periodsAvailable?: number;
  sourceRecordIds: string[];
  calculationVersion: string;
};
```

The detail view must provide an evidence link or table for the key values used in the narrative.

## 12. Proposed Backend/API Work

### Phase A — Analysis contracts

- Define typed response models for story, scope contribution, KPI drivers, issue classification, trend, opportunity, and evidence.
- Centralize direction-aware gap and weighted-impact calculations in a service layer.
- Reuse current KPI configurations and historical performance records.
- Add calculation-version metadata to protect historical reproducibility.

### Phase B — Scoped analysis endpoints

Recommended read endpoints:

- `GET /api/insights/summary`
- `GET /api/insights/geography-contribution`
- `GET /api/insights/team-contribution`
- `GET /api/insights/kpi-drivers`
- `GET /api/insights/population`
- `GET /api/insights/opportunities`
- `GET /api/insights/evidence/{insight_id}`

All endpoints must accept the same scope object and return the applied scope in the response.

### Phase C — Data and configuration quality

- Return explicit data-confidence flags.
- Detect missing targets, invalid weights, duplicate KPI keys, and incomplete employee mapping.
- Keep data issues separate from performance issues.
- Add server-side pagination for employee-level evidence.

## 13. Proposed Frontend Work

### Phase A — Progressive shell

- Replace the crowded filter row with context filters plus `More filters`.
- Add scope summary and active filter chips.
- Add loading, empty, partial-data, and configuration-error states.
- Keep URL state synchronized with filters and drill-down selections.

### Phase B — Executive and contribution views

- Executive Story card.
- Geography Contribution card.
- Team Contribution table.
- KPI Drivers panel.
- Data Confidence card.

### Phase C — Diagnostics and actions

- Issue-type badges.
- Trend/persistence timeline.
- Population spread/concentration view.
- Opportunity scenario cards.
- Recommended Action panel with links to existing workflows.

### Interaction rules

- Clicking a geography sets the geography scope.
- Clicking a team sets the team scope.
- Clicking a KPI sets a single KPI diagnostic scope.
- Clicking an employee opens the existing Employee Profile.
- Back navigation removes only the last drill-down level.
- Preserve filter state when navigating to evidence and returning.

## 14. Testing Strategy

### Calculation tests

- Higher-better and lower-better gap calculations.
- KPI achievement caps.
- Weighted contribution normalization.
- Geography/team aggregation.
- Coverage and missing-target handling.
- Persistence and trend classification.
- Opportunity scenario lift and cap behavior.

### API tests

- Scope consistency across all insight endpoints.
- Permission enforcement.
- Empty and partial-data responses.
- Pagination and evidence links.
- Historical reproducibility by calculation version.

### UI tests

- Cascading filter options.
- Progressive filter visibility.
- URL state and browser back behavior.
- Drill-down path: Company → Region → Team → KPI → Employee.
- Correct empty, loading, and partial-data states.
- No duplicate or conflicting filters.

### Release checks

- Frontend typecheck.
- Lint.
- Unit and integration tests.
- Production build.
- Browser smoke test for executive, team, KPI, and evidence flows.
- Verify calculations against a fixed reference dataset.

## 15. Delivery Sequence

1. Freeze and document the calculation contract.
2. Build backend aggregation services and typed responses.
3. Add reference-data tests for current teams, RCM, Pre-Approvals, Call Center, and Marketing.
4. Implement the progressive filter shell.
5. Implement Executive Story and contribution views.
6. Implement KPI diagnostics and issue classification.
7. Implement trends, population analysis, and data confidence.
8. Implement opportunities and recommended actions.
9. Run full regression and browser verification.
10. Release behind a feature flag and compare against the existing Insights page.

## 16. Acceptance Criteria

- A manager can understand the overall problem without opening a detailed table.
- The first screen has no more than four primary filters.
- Selecting a region changes the available teams and the story consistently.
- Selecting a team reveals KPI drivers rather than dumping all records.
- Selecting a KPI reveals affected population, trend, issue type, evidence, and action.
- Contribution percentages reconcile within rounding tolerance.
- Missing data never appears as a performance failure without an explicit data-quality label.
- Every narrative number can be traced to evidence.
- The system distinguishes severity from business impact.
- The user can reach the original employee/team workflows without losing scope context.
- No insight is generated when the minimum data-confidence requirements are not met.

## 17. Initial Release Recommendation

Start with a deterministic MVP covering:

- Executive Story.
- Geography Contribution.
- Team Contribution.
- KPI Drivers.
- Data Confidence.
- Progressive filters and URL-backed drill-down.

Defer automated root-cause language and opportunity forecasting until the calculation and evidence layers are validated against real management decisions.
