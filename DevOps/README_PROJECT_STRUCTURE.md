# PMS Dashboard Project Structure

This guide maps the current monorepo and points to the main implementation paths. For the current release and architecture summary, see [`PROJECT_SUMMARY.md`](../../PROJECT_SUMMARY.md).

## Runtime shape

```text
Frontend (React + TypeScript)
        |
        | HTTP + Socket.IO
        v
Backend (FastAPI + services + repositories)
        |
        +-- PostgreSQL
        +-- Redis
        +-- JSON team configs / fallback data
```

Main entry points:

- Frontend: `Frontend/src/main.tsx`
- Frontend routes/providers: `Frontend/src/App.tsx`
- Backend app: `Backend/app.py`
- Backend ORM schema: `Backend/models/models.py`

## Top-level layout

```text
PMS_Dashboard/
|-- Backend/
|-- Frontend/
|-- DevOps/
|-- Database/
|-- NEW_TEAM_ONBOARDING.md
|-- THREE_TEAMS_KPI_CALCULATION_GUIDE.md
`-- setup_project.ps1
```

## Backend

```text
Backend/
|-- api/
|   |-- middleware/     # auth, request timing, error handling
|   `-- routers/        # FastAPI route modules
|-- config/
|   |-- teams/          # config-driven team definitions
|   |-- database.py
|   |-- loader.py
|   |-- logging_config.py
|   `-- socket_config.py
|-- data_cleaning/      # shared cleaning framework
|-- Data_Cleaning_Teams/# team-specific cleaners
|-- migrations/         # Alembic revisions
|-- models/             # ORM models and Pydantic schemas
|-- processors/         # Excel ingestion orchestration
|-- repositories/       # persistence access layer
|-- services/           # business logic
|-- tests/              # backend tests
|-- utils/
|-- app.py
`-- requirements.txt
```

### Backend responsibilities

- `api/routers/performance.py`
  Performance endpoints, dashboards, employee history, and Balanced Scorecard APIs
- `services/performance_service.py`
  Standard dashboard aggregation
- `services/balanced_scorecard_service.py`
  Standard BSC response shaping from authorized records
- `services/management_bsc_service.py`
  Managerial/Corporate BSC config + snapshot runtime, history, imports, and Management Overview behavior
- `services/team_service.py`
  Team CRUD with config-backed payload building
- `services/team_onboarding_service.py`
  Team onboarding workflow state and execution
- `processors/` + `data_cleaning/`
  Excel-to-record ingestion path

### Key backend data flows

```text
Excel upload
  -> processor
  -> cleaner factory
  -> team-specific cleaner
  -> normalized KPI rows
  -> KPI/performance services
  -> PostgreSQL tables
```

```text
Team config JSON
  -> config loader
  -> team service / BSC services
  -> frontend config + dashboard responses
```

## Frontend

```text
Frontend/
|-- public/
|-- src/
|   |-- components/
|   |   |-- balanced-scorecard/
|   |   |-- common/
|   |   |-- employee/
|   |   |-- executive/
|   |   |-- notifications/
|   |   |-- team/
|   |   `-- team-management/
|   |-- context/
|   |-- hooks/
|   |   `-- api/
|   |-- lib/
|   |-- pages/
|   |-- schemas/
|   |-- services/
|   |-- store/
|   |-- types.ts
|   |-- App.tsx
|   |-- config.ts
|   |-- index.css
|   `-- main.tsx
|-- package.json
`-- vite.config.ts
```

### Frontend routes

Routes in `Frontend/src/App.tsx`:

- `/login`
- `/executive`
- `/team/:teamId`
- `/employee/:employeeId`
- `/planning`
- `/team-management`
- `/settings`

Role behavior:

- `Agent` users are forced to their own employee page
- `Admin`, `Manager`, and `Executive` can access the broader dashboard shell
- Team management is admin-only

### Balanced Scorecard frontend

Main BSC files:

- `Frontend/src/components/team/BalancedScorecardWorkspace.tsx`
- `Frontend/src/components/balanced-scorecard/StrategyMapView.tsx`
- `Frontend/src/components/balanced-scorecard/BSCRightRail.tsx`
- `Frontend/src/components/balanced-scorecard/KpiTablePanel.tsx`
- `Frontend/src/components/balanced-scorecard/KpiTrendPanel.tsx`
- `Frontend/src/components/balanced-scorecard/ManagerRosterPanel.tsx`
- `Frontend/src/components/balanced-scorecard/ManagerSummarySection.tsx`
- `Frontend/src/hooks/api/useBalancedScorecard.ts`

Current BSC behavior:

- `Corporate` drives Strategic Overview
- `Managerial` drives Management Overview
- Management Overview is manager-centric: selecting a manager updates KPI cards, details, and rail state from live API data
- The page title for Strategic Overview uses the highest available position in the team when present

## DevOps docs

```text
DevOps/
|-- README.md
|-- DATABASE_SCHEMA.md
|-- README_PROJECT_STRUCTURE.md
|-- SYSTEM_STATUS.md
|-- compose/
|-- deployment/
|-- docker/
|-- docs/
|-- monitoring/
|-- nginx/
`-- scripts/
```

Use `DevOps/docs/` for deep dives and runbooks. The four root docs in `DevOps/` should stay concise and current.
