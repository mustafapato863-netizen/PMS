# Admin branch and function permissions: QA and security review

Date: 2026-10-06. PR: #22.

## Scope

Admin user creation/editing, Manager branch/team assignments, Function Viewer grants,
role transitions, authorization middleware, scoped performance reads and cache isolation.
Tests use DOM component rendering and an in-process API with an isolated SQLite database.
This review does not claim a penetration test of the deployed production environment.

## Findings fixed

| Finding | Resolution |
| --- | --- |
| Historical Manager branch grants survived role changes and could return on a later promotion | Clear team assignments when leaving Manager/General Manager; entering Manager accepts only explicit grants |
| Team drilldown swallowed access-denied exceptions and returned HTTP 200 | Preserve HTTP 403 for denied access |
| Three frontend dependency vulnerabilities | Patch brace-expansion to 5.0.12, source-map-js to 1.2.2 and undici to 7.30.0 |

## Verification

| Check | Result |
| --- | --- |
| Admin form/panel edit and grant payload tests | 10 passed |
| Admin routing, function scope, performance reads, migration graph, existing security findings, General Manager and RBAC tests | 69 passed |
| Non-admin permission edits with forged Admin headers | Denied for Function Viewer, Manager and General Manager |
| Unauthenticated performance access with an Admin header | HTTP 401 |
| Out-of-function records, employee history and catalog | No unauthorized data returned |
| Out-of-function team drilldown | HTTP 403 |
| Grant revocation using the same existing token and populated summary cache | Subsequent records, summary and catalog return no data |
| Role transitions with historical branch rows | Historical grants do not return |
| Frontend lint, typecheck, complete test suite and production build/bundle budget | Passed locally; final commit also requires full GitHub CI |
| npm dependency audit after patches | 0 vulnerabilities |
| Python dependency audit of requirements.txt | No known vulnerabilities |

No unresolved findings remain within this tested scope. The optional Graphify command
was unavailable in the test workspace; no existing graph output was present.
