# PMS Dashboard Monorepo

The repository contains the complete PMS Dashboard delivery stack:

- `Frontend/`: React, TypeScript, and Vite application.
- `Backend/`: FastAPI, SQLAlchemy, Alembic, KPI scoring, uploads, reporting, and Socket.IO.
- `DevOps/`: container images, reverse-proxy configuration, deployment runbooks, and operational scripts.
- `docker-compose.yml`: live Dokploy-managed backend, worker, migration, and Redis stack behind Dokploy's Traefik gateway.
- `compose.production.yml`: separate Hostinger VPS/Caddy full-stack deployment profile (manual-only).

Frontend and Backend remain independently buildable services and share version control in this repository. The active Dokploy profile deploys the backend stack; the separate Hostinger/Caddy profile builds a full stack.

See [Project Summary](PROJECT_SUMMARY.md) for the single current overview of architecture, scoring rules, delivered capabilities, and deployment boundaries.

The stable source snapshots from the former standalone repositories are preserved here as normal `Frontend/` and `Backend/` directories rather than submodules. Their earlier commit histories remain available in the original repositories.

## Deployment profiles

**Active Dokploy path:** `docker-compose.yml` is the backend-only stack used with Dokploy/Traefik. The deployment contains one-shot database migration, backend, worker, and Redis services. It requires Dokploy's external network and production environment variables; **do not use it as a local development Compose file**. CI checks migration ordering, Redis readiness, and host port exposure.

**Alternative manual Hostinger/Caddy path:** `compose.production.yml` provides the standalone frontend, backend, worker, Redis, migration, and Caddy gateway. See the [Hostinger VPS deployment runbook](DevOps/deployment/hostinger-vps.md). It must not be deployed alongside Dokploy on the same server.

Use `DevOps/.env.hostinger.example` only as a configuration template. Never commit production secrets.
