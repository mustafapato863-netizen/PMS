# PMS Project Summary

**Last updated:** 2026-08-09  
**Repository:** `mustafapato863-netizen/PMS`  
**Release model:** one monorepo, independently buildable services, atomic releases

## Purpose

PMS is a performance-management platform for employee, team, management, and executive scorecards. It ingests authorized operational workbooks, applies versioned KPI configuration, and presents direction-aware scores, grades, trends, insights, corrective actions, and reports.

## Runtime architecture

- `Frontend/`: React + TypeScript + Vite dashboard and authenticated route shell.
- `Backend/`: FastAPI + SQLAlchemy + Alembic services, repositories, KPI scoring, uploads, reporting, and Socket.IO.
- `Database/`: database scripts and migration support.
- `DevOps/`: Dockerfiles, Nginx, compose files, deployment runbooks, monitoring, backups, and operational scripts.
- `compose.production.yml`: production stack for the Hostinger VPS.

The normal request path is `Frontend -> Backend -> PostgreSQL/Supabase`. Redis is optional for caching and realtime scaling; bounded fallbacks keep local development usable when Redis is unavailable.

## Data and scoring rules

- PostgreSQL/Supabase is the source of truth for persisted performance evidence, users, configuration, historical periods, notifications, and actions.
- Team onboarding is configuration-driven through `Backend/config/teams/`; JSON files are fallback/seed inputs, not a replacement for persisted production data.
- KPI calculations are direction-aware, weight-aware, and capped at 100% achievement unless a team configuration explicitly defines another bounded rule.
- Effective KPI configuration and historical snapshots remain tied to the period being displayed; current configuration must not rewrite historical results.
- Missing data, invalid targets, unavailable comparisons, and real numeric zero are separate states.
- Authorization is applied before aggregation, trends, insights, exports, and employee-level views.

## Delivered product capabilities

- Executive, team, employee, managerial, and corporate Balanced Scorecard views.
- Progressive Insights analysis: executive scope first, then geography/team/KPI drill-down, affected people, trends, evidence, and actions.
- Configurable RCM and regional/team groupings with branch, function, level, employee, and KPI filtering.
- Employee presence, profiles, password/full-name management, action history, corrective actions, and quick actions.
- Workbook ingestion and team onboarding with validation and operational monitoring.
- Shared report evidence and report-builder blocks for score movement, weighted KPI impact, employee risk, trends, data quality, and evidence confidence.
- Scoped notifications and Socket.IO rooms with persisted notification records.

## Production and operations

- Hostinger VPS deployment is defined by `compose.production.yml` and the runbook in `DevOps/deployment/hostinger-vps.md`.
- Production secrets belong in the deployment environment only; commit `.env.example` templates, never credentials.
- Health endpoints, request IDs, structured logs, bounded Redis fallbacks, and non-root containers are part of the production baseline.
- Roll back application images first. Database downgrade or restore is allowed only after a validated backup, migration compatibility check, and integrity verification.

## Verification snapshot

The latest recorded release checks passed backend regression, frontend tests, type checking, linting, production build, bundle budgets, and browser layout/accessibility smoke tests. These numbers are historical evidence from the release checks, not a new test run performed by this documentation cleanup.

For reproducible verification, use the commands documented in `DevOps/README.md` and the active test suites under `Backend/tests/` and `Frontend/`.

## Source-of-truth pointers

- Frontend entry and routing: `Frontend/src/main.tsx`, `Frontend/src/App.tsx`.
- Backend entry and runtime configuration: `Backend/app.py`, `Backend/config/`.
- Database models and active migrations: `Backend/models/`, `Backend/migrations/`.
- Deployment contract: `compose.production.yml`, `DevOps/deployment/`, `DevOps/.env.hostinger.example`.
- Detailed operational references remain in `DevOps/docs/`; historical planning and audit files are intentionally not kept here.

New work should be tracked through GitHub issues and pull requests. This file is the single project-level summary; do not add another phase plan or status snapshot for routine changes.
