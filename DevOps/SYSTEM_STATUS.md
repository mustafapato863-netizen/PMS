# PMS Dashboard System Status

**Last verified:** July 6, 2026

**Lifecycle:** Active development

**Overall status:** Usable development build with a live modular Balanced Scorecard flow, manager-centric Management Overview, database-backed notifications, and config-driven team onboarding.

This document is a point-in-time engineering snapshot for the local workspace.

## Latest verification

The following checks were run locally on July 6, 2026:

| Check | Result | Notes |
| --- | --- | --- |
| Frontend production build | Passing | `npm run build` completed successfully |
| Frontend lint | Failing | `164 errors`, `7 warnings`; mostly older type/unused-code issues across the frontend |
| Backend focused regression suite | Partially passing | `112 passed`, `3 failed` in config-weight validation tests |

Commands used:

```powershell
cd Frontend
npm run build
npm run lint

cd ..\Backend
.\.venv\Scripts\python -m pytest tests\test_three_teams.py tests\test_submission_team.py tests\test_services.py -q
```

## Working capabilities

### Implemented

- FastAPI backend with Socket.IO integration
- React frontend with authenticated route shell and role-aware navigation
- PostgreSQL-backed dashboard and employee performance reads
- Redis cache with in-memory fallback when Redis is unavailable
- Config-driven team discovery through `Backend/config/teams/`
- Team onboarding workflow with persisted `onboarding_states`
- Admin user management with protections around the `super` account
- Notification persistence through `notifications` and `notification_recipients`
- Balanced Scorecard workspace for `Managerial` and `Corporate`
- Management BSC persistence through:
  - `management_kpi_config`
  - `management_kpi_config_history`
  - `management_kpi_snapshots`
- Manager-centric Management Overview where selected manager context updates KPI cards and related BSC detail state from live API data
- Strategy view title can use the highest detected position in the selected team context

### Verified scoring rules

Current unified KPI scoring behavior:

1. KPI achievement is capped at `100%` across all API and UI surfaces
2. Stored achievement is normalized to the global `0..1` range, including legacy rows when read
3. Effective achievement is capped at `100%` for contribution math
4. KPI contribution cannot exceed its configured weight share
5. Final score is the sum of contributions and cannot exceed `100%`

## Supported teams

Current config-backed teams in `Backend/config/teams/`:

- Inbound
- Outbound
- Inbound UAE
- Pre-Approvals IP Offshore
- Sales
- Pharmacy
- Coding
- CSR
- Submission

## Current known issues

- Frontend lint debt remains broad and is not isolated to one page or feature
- The three failing backend tests are config validation expectations in `tests/test_three_teams.py`:
  - weights below tolerance should fail but currently pass
  - empty KPI list should fail but currently pass
  - single KPI weight below `1.0` should fail but currently pass
- The live notification experience still depends on an active browser Socket.IO connection for real-time delivery
- Several docs previously referenced older BSC/demo behavior; those references are being normalized to the modular workspace

## Current priorities

1. Clean up frontend lint debt without destabilizing the current working dashboard flows.
2. Keep BSC behavior tied to real config/snapshot data rather than fallback demo logic.
3. Tighten team-config validation so the failing weight tests match runtime expectations.
4. Continue normalizing root docs and runbooks around the current monorepo structure.
5. Preserve the config-first team onboarding path for new teams.

## Infrastructure status

Active today:

- single-table `performance_records` with partition-ready key design
- application-level authorization and scoping
- dynamic query-time summary building
- local Compose and manual frontend runtime

Not the active primary deployment model yet:

- database-level RLS
- materialized views
- trigger-first auditing and weight enforcement
- horizontally scaled Socket.IO pub/sub deployment

## Local runtime reference

From the repo root:

```powershell
docker compose up --build
```

Frontend:

```powershell
cd Frontend
npm run dev
```

Default frontend API/socket target remains `http://localhost:8000` unless overridden by `VITE_API_BASE_URL` and `VITE_SOCKET_URL`.

## Status policy

- Update this file only from commands actually run in the current workspace.
- Do not record fixed pass rates, uptime claims, or production-readiness claims without fresh evidence.
