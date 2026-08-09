# PMS Dashboard DevOps Docs Hub

This `DevOps/` folder is the operational and architecture reference for the PMS Dashboard monorepo. It does not contain the live frontend or backend implementation; it documents how the running system is structured, verified, deployed, and supported.

## What the app currently includes

- React + TypeScript frontend in `Frontend/`
- FastAPI backend in `Backend/`
- PostgreSQL-backed performance data
- Redis-backed caching with in-memory fallback
- Socket.IO notifications persisted to the database
- Config-driven team onboarding through `Backend/config/teams/`
- Modular Balanced Scorecard workspace for `Managerial` and `Corporate`
- Manager-centric Management Overview backed by live BSC config and snapshot tables

## Start here

- [`PROJECT_SUMMARY.md`](../PROJECT_SUMMARY.md): single current project and release summary
- [`README_PROJECT_STRUCTURE.md`](D:/Projects/PMS_Dashboard/DevOps/README_PROJECT_STRUCTURE.md): where code and responsibilities live
- [`DATABASE_SCHEMA.md`](D:/Projects/PMS_Dashboard/DevOps/DATABASE_SCHEMA.md): main database tables, relationships, and BSC persistence
- [`docs/API_REFERENCE.md`](D:/Projects/PMS_Dashboard/DevOps/docs/API_REFERENCE.md): backend route reference
- [`docs/Architecture.md`](D:/Projects/PMS_Dashboard/DevOps/docs/Architecture.md): higher-level system flow

## Folder map

```text
DevOps/
|-- README.md
|-- DATABASE_SCHEMA.md
|-- README_PROJECT_STRUCTURE.md
|-- compose/        # legacy development and staging compose files
|-- docker/         # backend and frontend Dockerfiles
|-- deployment/     # platform-specific deployment notes
|-- docs/           # architecture, API, security, troubleshooting, roadmap
|-- monitoring/     # Prometheus / Grafana / Loki config
|-- nginx/          # reverse proxy config
|-- scripts/        # deploy / backup / restore / migrate helpers
|-- backups/        # backup target
`-- restore/        # restore target
```

## Local runtime

Infrastructure services and the backend can be started from the repo root:

```powershell
docker compose up --build
```

Frontend runs separately:

```powershell
cd Frontend
npm run dev
```

Useful validation commands:

```powershell
cd Frontend
npm run build
npm run lint

cd ..\Backend
.\.venv\Scripts\python -m pytest tests\test_three_teams.py tests\test_submission_team.py tests\test_services.py -q
```

The canonical production definition is `compose.production.yml` at the repository root. Do not use the legacy environment-specific Compose files for production.

## Documentation policy

- Treat `Backend/models/models.py` and active migrations as the source of truth for schema details.
- Treat `Frontend/src/App.tsx` and `Backend/app.py` as the source of truth for runtime structure.
- Keep `PROJECT_SUMMARY.md` current when architecture or release boundaries change.
- Keep old demo-only BSC notes out of the main docs flow; the live implementation is now the modular workspace.
