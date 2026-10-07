# Release verification — 8 October 2026

Scope: accumulated executive summary, function cards, filters, scoped access,
roster caching, team hierarchy, and mandatory first-login password changes.

## Checks run before merging

- Backend: 949 passed, 1 skipped with the CI configuration (automatic seeding
  disabled, scoped API rollout disabled for the legacy test suite, `CI=true`).
- Frontend: 573 passed across 82 test files, using one worker.
- Frontend type checking, lint, production build, bundle budgets and whitespace
  checks passed. The existing approximately 504kB entry-chunk warning remains.
- Local Chromium workflow suite: 23 checks passed, including cached eight-row
  pagination, inline team expansion, filter cascades, return-home navigation,
  responsive filters, and Branch Director UI/backend access boundaries.
- Local Chromium design suite: 8 checks passed for static labelled function
  charts, interactive hero keyboard controls, light/dark themes, and responsive
  layouts at 390, 768, 1024 and 1440 pixels.
- First-login redirect test fixture now publishes logout state reactively,
  matching the real authentication provider; the previous intermittent redirect
  failure did not recur in the full suite. Production timeouts were not changed.
- Both new migrations were exercised against a temporary local PostgreSQL schema
  inside a rolled-back transaction. Upgrades preserved legacy users, existing
  accounts defaulted to no forced password change, supported downgrades passed,
  and downgrade with newer roles was rejected without changing accounts. The
  temporary schema was rolled back and existing tables were untouched.
- Changed file paths and recognizable private-key/access-token signatures were
  checked; no secret files or recognized credential signatures were found. This
  is a release hygiene check, not an exhaustive security audit.

## Deployment prerequisites and limits

The user confirmed that Dokploy runs `alembic upgrade head` before starting new
backend code. The required head is `c8d3f6a1b205`, following `b7e2d6a9f104`.
No production data-fix script or database downgrade was run.

The scoped roster endpoint requires `PMS_SCOPED_PERFORMANCE_API_ENABLED=true` on
the deployed backend. Production feature flags and authenticated user workflows
must be verified independently; local checks are not production certification.

The separate Hostinger GitHub deployment workflow has no configured production
secrets/variables. This is independent of the existing Vercel/Dokploy deployment.

Known unrelated local limitations: the optional executive-summary endpoint uses
its fallback; the aggregate RCM team-actions endpoint returns 404. Neither was
treated as a successful API response or corrected by this release.
