# Authentication and Cookie Decision

Date: 2026-07-29
Decision status: retain bearer JWT for this optimisation phase; harden immediately and evaluate a cookie migration as a separate security change.

## Current design

- Login returns a JWT.
- Frontend stores the JWT and session object in `localStorage`.
- `apiFetch` adds `Authorization: Bearer`.
- Backend validates signature/expiry and reloads the active user from PostgreSQL.
- Redis session presence is enforced only when Redis is available; otherwise a valid JWT is trusted until expiry.
- Logout clears browser authentication values but not the React Query cache.

## Decision rationale

Moving to cookies affects CSRF, CORS, domain topology, local development, refresh, logout, socket authentication and deployment configuration. The current task prohibits speculative authentication changes and requires no security weakening. Therefore:

1. keep the established bearer contract for compatibility,
2. close its known cache/configuration gaps,
3. design and test any HttpOnly cookie migration separately.

## Immediate requirements

- Production startup must fail when `JWT_SECRET` is missing, default or too weak.
- Clear TanStack Query user data on logout and terminal 401.
- Keep short token expiry and define re-authentication behaviour.
- Never log tokens or authorization headers.
- Apply a strict Content Security Policy and eliminate unsafe script injection paths.
- Keep backend role/team authorization authoritative.
- Make Redis session semantics explicit: either required and fail closed, or optional revocation with documented maximum JWT lifetime.

## Cookie migration criteria

Prefer an HttpOnly, Secure, SameSite cookie when:

- frontend and API domains are known,
- allowed origins are explicit,
- CSRF protection is implemented and tested,
- logout/revocation is reliable,
- local/staging/production cookie domains are documented,
- Socket.IO and download flows use the same authenticated session safely.

If frontend and API are cross-site, `SameSite=None; Secure` requires explicit CSRF defenses and credentialed CORS. Do not enable wildcard origins.

## Recommended target

- short-lived HttpOnly access/session cookie,
- server-side revocation or refresh rotation,
- CSRF token/header for state-changing requests,
- explicit Secure/SameSite/domain/path settings by environment,
- no authentication token readable by JavaScript,
- query cache cleared on identity change.

This is a security migration, not a performance optimisation, and requires its own compatibility and rollback gate.
