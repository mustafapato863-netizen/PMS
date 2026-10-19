# New Team Onboarding Guide

Use this guide to add a new team with the fewest possible changes and without breaking the existing Balanced Scorecard flow.

## Source of Truth

- Team config JSON: `Backend/config/teams/*.json`
- Team CRUD and config-backed team payloads: `Backend/services/team_service.py`
- Team onboarding workflow API: `POST /api/team-management/teams/{team_name}/onboard`
- Team onboarding status API: `GET /api/team-management/teams/{team_name}/onboarding-status`
- Config discovery API: `GET /api/config/teams`
- Team registry API: `GET /api/team-management/teams`
- Management BSC config API: `GET /api/team-management/bsc/configs`
- Management BSC runtime service: `Backend/services/management_bsc_service.py`
- Team-specific cleaners: `Backend/Data_Cleaning_Teams/`

Team onboarding is config-first. Add code only when the Excel shape or KPI logic genuinely cannot be expressed in JSON.

## Current Baseline

As of July 2026, the system supports twelve config-driven teams:

- Inbound
- Outbound
- Pre-Approvals IP Offshore
- Sales
- Pharmacy
- Coding
- CSR
- Submission
- Re-Submission
- Pre-Approvals OP Dubai
- Pre-Approvals IP Final Dubai
- Marketing

The frontend already expects:

- `Employee` KPIs for the standard team dashboard and employee profile
- `Managerial` and `Corporate` performance levels for the Balanced Scorecard workspace
- BSC perspectives to come from config and runtime snapshot data, not hardcoded frontend cards

## Required Team Config Shape

Create one JSON file under `Backend/config/teams/`.

Minimum root fields:

- `team`
- `db_name`
- `region`
- `employee_id_col`
- `employee_name_col`
- `grade_thresholds`
- `kpis`

If the team will use Balanced Scorecard views, also add:

- `performance_levels.Managerial`
- `performance_levels.Corporate`

Each BSC performance level should contain:

- `balanced_scorecard.enabled`
- `balanced_scorecard.perspectives`
- `balanced_scorecard.strategy_map_links`
- `kpis`

Each KPI entry should include:

- `key`
- `label`
- `weight`
- `direction`
- `unit`
- `color`
- `actual_col`
- `target_col`
- `aggregation.method`

Valid team-dashboard aggregation methods:

- `ratio`: rate calculated from pooled volumes. Requires `numerator_col` and `denominator_col`.
- `weighted_average`: average weighted by operational volume. Requires `weight_col`.
- `sum`: additive volumes such as handled queries or revenue.
- `average`: non-additive observations such as quality audit scores.

Use `$geo.bookings`, `$geo.attended`, `$calls.total_handled`, and `$calls.abandoned`
when the source is a normalized AgentRecord field rather than a raw Excel column.
Never choose `average` for a rate when its numerator and denominator are available.
For `ratio` and `weighted_average`, use the exact column names persisted in API
`raw_data` after cleaning; they may differ from the original workbook headers.
Confirm those configured sources are populated in a processed sample before approval.

Managerial and Corporate BSC KPI entries must also include:

- `perspective`

Valid BSC perspective keys:

- `Financial`
- `Customer`
- `Internal Process`
- `Learning & Growth`

Keep KPI weights summing to `1.0` within each level.

## Important Lessons From Real Onboarding Work

Submission and the later BSC rollout exposed the rules we should now treat as standard:

1. Excel column names are not universal. Always read employee ID and employee name from the team config first.
2. Raw KPI keys, display labels, and weight lookup keys can differ. Frontend and backend mapping must tolerate canonical and legacy names when needed.
3. Rows with `Performance Grade` equal to `-`, `New Staff`, or `Leave` must be filtered during ingestion, before scoring.
4. BSC cards and trends should render from actual config plus snapshot data. Do not reintroduce hardcoded perspective cards or fake KPI history.
5. If the team needs Managerial or Corporate BSC, onboarding is not complete until both config and snapshot/config tables can produce live BSC output.

## Minimal Onboarding Flow

1. Add the team JSON in `Backend/config/teams/`.
2. Confirm the config loads through `GET /api/config/teams`.
3. Create the team through the normal team-management flow.
4. Verify the created team appears in `GET /api/team-management/teams`.
5. Upload a sample workbook and confirm the cleaner maps columns correctly.
6. Verify `Employee` dashboard KPIs and score calculations.
   - reconcile every team rate as pooled numerator ÷ pooled denominator
   - confirm current, previous, trend, and baseline use the configured aggregation
7. If BSC applies to the team, verify both `Managerial` and `Corporate` levels:
   - perspectives load
   - KPI table loads
   - scorecard state is not empty for the loaded period
   - management selection can switch the KPI cards for a selected manager
8. Run the onboarding workflow endpoint only after config and sample data are ready.

## When Code Changes Are Actually Needed

Only add code when the new team has one of these:

- a different Excel structure that existing cleaners cannot parse
- a KPI formula that cannot be expressed with the current model
- a new cleaner requirement
- a special display rule that config cannot express
- a safe compatibility mapping requirement between stored KPI keys and displayed labels

Do not add a team-specific branch just because one sample file looks different once.

## Verification Checklist

- `GET /api/config/teams` returns the new team
- `GET /api/team-management/teams` returns the new team
- uploaded rows create usable performance data
- employee IDs and names map correctly
- grade exclusions are applied before scoring
- employee dashboard renders expected KPIs
- employee profile renders expected KPI history
- BSC renders for every supported performance level the team is supposed to have
- no empty or unauthorized BSC state appears for valid in-scope users

## Quick Checks

```powershell
cd Backend
pytest tests/test_three_teams.py -q
pytest tests/test_submission_team.py -q
pytest tests/test_services.py -q

cd ..\Frontend
npm run build
```

If the new team includes Management BSC data, also verify the relevant BSC endpoints and UI flow with a real uploaded period before calling onboarding complete.
