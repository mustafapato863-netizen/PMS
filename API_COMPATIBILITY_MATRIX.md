# API Compatibility Matrix

Date: 2026-07-29
Sources: live local OpenAPI (118 operations) and active Frontend request call sites.

## Contract conventions

| Concern | Backend reality | Frontend reality | Status |
|---|---|---|---|
| Authentication | Bearer JWT | JWT from `localStorage` | Compatible, security hardening required |
| User role | Derived from active DB user | Also sends `X-User-Role` | Compatible; header is redundant |
| Success envelope | Mostly `{success,message,data}` | Most hooks expect this envelope | Mostly compatible |
| Validation errors | FastAPI `detail` | API client supports `detail` | Compatible |
| Middleware errors | `{success,message[,request_id]}` | API client supports `message` | Compatible but inconsistent |
| Cancellation | Native fetch signal possible | Not applied uniformly | Gap |
| Query caching | TanStack Query for primary hooks | Manual calls bypass it | Gap |

## Active frontend routes

| Frontend consumer | Method/path | OpenAPI match | Response expectation | Result |
|---|---|---|---|---|
| AuthContext | POST `/api/auth/login` | Exact | standard envelope/token | Pass |
| AuthContext | GET `/api/auth/me` | Exact | standard envelope/user | Pass |
| AuthContext | PUT `/api/auth/profile` | Exact | standard envelope | Pass |
| AuthContext | POST `/api/auth/profile/password` | Exact | standard envelope | Pass |
| User management | `/api/users/*` | Exact family | mixed standard envelopes | Pass |
| Sidebar/config | GET `/api/config/teams` | Exact | standard envelope/configs | Pass |
| Team config | GET `/api/config/teams/{team}` | Exact | standard envelope/config | Pass |
| KPI weights | GET `/api/settings/weights` | Exact | standard envelope/list | Pass |
| KPI targets | GET `/api/settings/targets` | Exact | standard envelope/list | Pass |
| Performance hook | GET `/api/performance` | Exact | full record list | Pass; oversized |
| Employee profile hook | GET `/api/employee/{id}/` | Backend route omits trailing slash | standard envelope/profile | Redirect risk |
| Employee profile page | GET `/api/employee/{id}` | Exact | standard envelope/profile | Pass |
| Balanced scorecard | GET `/api/performance/balanced-scorecard` | Exact | standard envelope/BSC | Pass |
| Insights | GET `/api/insights/workspace` | Exact | typed Insights envelope | Pass; slow/large |
| Planning options | GET `/api/planning/options` | Exact | standard envelope/options | Pass; slow |
| Planning list/detail | GET `/api/planning[/{id}]` | Exact | standard envelope | Pass |
| Planning mutations | POST/PUT/PATCH/DELETE `/api/planning/*` | Exact family | standard envelope | Pass |
| Reports options | GET `/api/reports/options` | Exact | standard envelope/options | Pass; slow |
| Reports list | GET `/api/reports` | Exact | standard envelope/page | Pass |
| Reports preview/generate | POST `/api/reports/{preview|generate}` | Exact | standard envelope | Pass |
| Story builder | `/api/reports/story/*` | Exact family | standard envelope | Pass |
| Team management | `/api/team-management/teams*` | Exact family | dedicated team schemas | Pass; frontend typings should remain route-specific |
| Upload history | GET `/api/uploads/` | Exact | standard envelope | Pass |
| PMS upload | POST `/api/uploads/pms` | Exact | standard envelope | Pass; manual fetch path |
| BSC template upload | POST `/api/performance/balanced-scorecard/template/upload` | Exact | standard envelope | Pass; manual multipart |
| Notifications | `/api/users/notifications*` | Exact family | standard envelope | Pass |
| Corrective actions | `/api/corrective-actions*` | Exact family | standard envelope | Pass |
| Performance export | GET `/api/performance/export` | Exact | binary response | Pass; manual fetch required |
| Global search | GET `/api/search/global` | Exact | standard envelope/search data | Pass |
| Web vitals | POST `/api/vitals` | Exact | no consumer body dependency | Pass |

## Compatibility defects and actions

### C1: Trailing-slash redirect

`useEmployeeProfile` calls `/api/employee/{id}/`, while OpenAPI declares `/api/employee/{id}`. Normalize the frontend path to avoid an extra redirect and preserve authorization headers across intermediaries.

### C2: Error-envelope fragmentation

Define one error schema with:

```json
{
  "success": false,
  "message": "Human-safe message",
  "code": "STABLE_MACHINE_CODE",
  "request_id": "optional-correlation-id",
  "details": []
}
```

Do not remove legacy parsing until all active clients are migrated.

### C3: Two request clients

`apiFetch` handles token injection, 401 teardown and JSON parsing. `fetchWithRole` is still required for binary/multipart calls but is also used for normal JSON reads. Converge JSON traffic on `apiFetch`; retain a shared raw-response helper for upload/download.

### C4: Query cache isolation

TanStack Query keys do not include the authenticated user and its cache is not cleared on logout. Clear it during logout/401 teardown before another user can sign in on the same browser.

### C5: Duplicate performance surface

For the measured June scope, `/api/performance` and `/api/performance/records` return the same 597,829-byte representation. Keep both routes for compatibility but designate one canonical route and avoid calling both on the same page.

## Compatibility gate

No active frontend route was found to be absent from OpenAPI. Release is blocked only on the high-risk security/configuration issues documented in the current-state audit, not on a missing active endpoint.
