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

The shared bounded roster endpoint is authenticated and scope-enforced regardless
of `PMS_SCOPED_PERFORMANCE_API_ENABLED`. That flag still controls the new dashboard
summary/history paths. Deploy the backend roster compatibility fix along with its
frontend before verifying employee availability. Production feature flags and
authenticated user workflows must be verified independently; local checks are
not production certification.

The separate Hostinger GitHub deployment workflow has no configured production
secrets/variables. This is independent of the existing Vercel/Dokploy deployment.

Known unrelated local limitations: the optional executive-summary endpoint uses
its fallback; the aggregate RCM team-actions endpoint returns 404. Neither was
treated as a successful API response or corrected by this release.

## Local follow-up: employee availability and KPI pagination

- The bounded records route is available with dashboard rollout disabled, while
  retaining authenticated server scopes, cursor limits and scope-specific caches.
- Role/API regressions: 132 passed, covering director filter tampering and revoked
  grants with rollout enabled/disabled, Manager level isolation, Employee self-only
  reads, global roles, anonymous denial and bounded pagination.
- Full frontend: 615 passed (84 files). After correcting mobile employee grid
  overflow, the relevant component/page suite passed 54 checks.
- Typecheck, lint, production build and bundle budgets passed. Existing large
  entry-chunk warning remains.
- Local Chromium: employees and KPIs show eight rows per page; switching pages
  uses cached data. Verified 1440/768/375px with no page overflow or JS errors.
- No production release in this follow-up. Both backend and frontend changes must
  be published before these fixes can be verified on the live system.
