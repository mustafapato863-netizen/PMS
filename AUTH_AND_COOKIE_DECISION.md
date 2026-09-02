# Authentication and Cookie Decision

Date: 2026-07-29
Decision status: the refresh-cookie flow is now implemented for browser sessions; keep the access token in memory and retain the documented compatibility migration for legacy localStorage tokens.

## Current design

- Login returns a short-lived JWT and sets refresh/CSRF cookies.
- Frontend keeps the access JWT in memory and sends it as `Authorization: Bearer`.
- The refresh token is `HttpOnly`, `Secure`, and configured with an explicit SameSite policy; it is never written to browser storage.
- The CSRF token is retained in `localStorage` so a split-origin frontend can send the required header; it is not an authentication credential.
- The cached user/profile and role are stored only to render the shell quickly; `/api/auth/refresh` and `/api/auth/me` remain authoritative on every page load.
- Refresh requests are coalesced so concurrent requests cannot rotate the same refresh-token family more than once.
- Backend validates signature/expiry and reloads the active user from PostgreSQL.
- Logout clears browser authentication values and the React Query cache.

## Decision rationale

The browser session uses a hybrid flow: a short-lived bearer access token remains in memory for API compatibility, while the long-lived refresh credential is protected by an HttpOnly cookie. This avoids persistent authentication tokens in JavaScript-readable storage without requiring a breaking migration of every API request.

## Immediate requirements

- Production startup must fail when `JWT_SECRET` is missing, default or too weak.
- Clear TanStack Query user data on logout and terminal 401.
- Keep short token expiry and define re-authentication behaviour.
- Never log tokens or authorization headers.
- Apply a strict Content Security Policy and eliminate unsafe script injection paths.
- Keep backend role/team authorization authoritative.
- Make Redis session semantics explicit: either required and fail closed, or optional revocation with documented maximum JWT lifetime.

## Cookie requirements

The refresh-cookie flow requires:

- frontend and API domains are known,
- allowed origins are explicit,
- CSRF protection is implemented and tested,
- logout/revocation is reliable,
- local/staging/production cookie domains are documented,
- Socket.IO and download flows use the same authenticated session safely.

If frontend and API are cross-site, `SameSite=None; Secure` requires explicit CSRF defenses and credentialed CORS. Do not enable wildcard origins.

## Applied target

- short-lived bearer access token held only in memory,
- HttpOnly refresh cookie with server-side rotation and revocation,
- CSRF token/header for cookie-authenticated refresh and logout requests,
- explicit Secure/SameSite/domain/path settings by environment,
- no newly issued authentication token written to `localStorage`,
- cached profile data used only for fast initial rendering,
- query cache cleared on identity change.
