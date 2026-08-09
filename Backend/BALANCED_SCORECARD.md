# Balanced Scorecard Backend Contract

Balanced Scorecard is available only for `Managerial` and `Corporate` performance levels.

## Configuration

Team JSON is the sole source of BSC metadata. A configured level contains:

- `balanced_scorecard.enabled`
- four ordered `balanced_scorecard.perspectives`
- optional `balanced_scorecard.strategy_map_links`
- `perspective` and optional `rollup` (`average`, `sum`, `latest`) on every BSC KPI

Database KPI configuration is not a second metadata source. Performance records and KPI values remain the source for actuals, targets, raw achievement, and capped weighted contribution.

## API

`GET /api/performance/balanced-scorecard`

Required query parameters: `team`, `performance_level`, and `year`. Optional parameters: `month`, repeated `employee_ids`, `history_months`, `selected_kpi`, and `branch=all`.

The endpoint requires an authenticated session. It rejects Employee, legacy-unscoped access, unauthorized team/level combinations, unsupported branch values, and employee IDs outside the authorized context.

## Aggregation

- Raw achievement remains uncapped for Balanced Scorecard analysis.
- Existing capped KPI contribution is the score input.
- Population KPI contribution is the mean valid contribution across selected people.
- Perspective and total scores divide summed contributions by measured configured weight.
- Coverage reports measured weight divided by configured weight.
- Missing values reduce coverage and remain `No Data`; they are never converted to zero.
- A perspective without configured KPIs is `Not Configured`.
- History ends at the selected month and year.

## Authorization

`UserTeamAssignment.performance_level` optionally narrows an assignment. `NULL` preserves the previous all-level team access. Level-specific assignments do not qualify a manager as a general manager, even when they cover every team.
