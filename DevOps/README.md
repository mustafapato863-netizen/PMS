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
- [`README_PROJECT_STRUCTURE.md`](README_PROJECT_STRUCTURE.md): where code and responsibilities live
- [`DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md): main database tables, relationships, and BSC persistence
- [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md): backend route reference
- [`docs/Architecture.md`](docs/Architecture.md): higher-level system flow

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

## Deployment profiles

- **Live Dokploy:** repository root `docker-compose.yml` manages backend, worker, migrations, and Redis behind Dokploy's Traefik. It requires the external `dokploy-network` and real deployment variables. **Do not run bare `docker compose up --build` on a developer workstation**; this is not a development Compose file.
- **Manual Hostinger/Caddy alternative:** root `compose.production.yml` includes frontend and TLS gateway. Follow [the manual Hostinger runbook](deployment/hostinger-vps.md); do not launch this stack on the Dokploy host.
- CI resolves both Compose files. It verifies Redis health, successful migration-before-API/worker startup, and loopback-only direct published application ports on the active Dokploy profile.

## Local development

Run application services independently using local development configuration (do not reuse production credentials):

```bash
cd Backend
python -m pip install -r requirements-dev.txt
python -m uvicorn app:app --reload
```

In another terminal:

```bash
cd Frontend
npm ci
npm run dev
```

Useful verification:

```bash
cd Backend
python -m pytest -q

cd ../Frontend
npm run lint
npm run typecheck
npm test
npm run build:ci
```

## Documentation policy

- Treat `Backend/models/models.py` and active migrations as the source of truth for schema details.
- Treat `Frontend/src/App.tsx` and `Backend/app.py` as the source of truth for runtime structure.
- Keep `PROJECT_SUMMARY.md` current when architecture or release boundaries change.
- Keep old demo-only BSC notes out of the main docs flow; the live implementation is now the modular workspace.
