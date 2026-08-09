# PMS Dashboard Monorepo

The repository contains the complete PMS Dashboard delivery stack:

- `Frontend/`: React, TypeScript, and Vite application.
- `Backend/`: FastAPI, SQLAlchemy, Alembic, KPI scoring, uploads, reporting, and Socket.IO.
- `DevOps/`: container images, reverse-proxy configuration, deployment runbooks, and operational scripts.
- `compose.production.yml`: Hostinger VPS production stack.

Frontend and Backend remain independently buildable services but are versioned and released atomically from this repository.

See [Project Summary](PROJECT_SUMMARY.md) for the single current overview of architecture, scoring rules, delivered capabilities, and deployment boundaries.

The stable source snapshots from the former standalone repositories are preserved here as normal `Frontend/` and `Backend/` directories rather than submodules. Their earlier commit histories remain available in the original repositories.

## Production deployment

See [Hostinger VPS deployment](DevOps/deployment/hostinger-vps.md) and use `DevOps/.env.hostinger.example` only as a template. Never commit production secrets.
