# Local performance and regression checks

`npm run test:e2e:performance` runs real Chromium against the existing local frontend and backend. Install Python Playwright and its Chromium browser first if they are not already available. Set `PMS_E2E_USERNAME` and `PMS_E2E_PASSWORD` in your terminal environment; do not put credentials in this repository.

Optional `PMS_E2E_BRANCH_USERNAME` and `PMS_E2E_BRANCH_PASSWORD` enable checks with an existing Dubai Branch Director account. Without them, branch checks are not run. No accounts, score records, actions, or configuration are created or modified. Normal sign-in creates an ordinary authentication session.

Defaults are frontend `http://127.0.0.1:5173` and backend `http://127.0.0.1:8000`. Override using `PMS_E2E_URL` and `PMS_E2E_API_URL`. Both URLs must be localhost: this suite refuses production targets.

The runner checks roster pagination/caching, inline team expansion, automatic team/function selection, level options, filter reset, team/function drilldowns, return-home data, interactive trend values, and responsive filter panels. Optional branch checks cover the locked branch, navigation restrictions, unavailable administrative content, and an out-of-scope API request returning either HTTP 403 or an empty result (never unauthorized rows/counts).

Reports are generated under ignored `e2e/artifacts/`. They include request paths/timings and assertion results, but exclude authentication responses, employee rows and pagination cursors. `--report name` changes the report name; `--inspect` is a shorter diagnostic run, not the full suite.

Timing measurements are observations from local Vite development mode, not production performance guarantees or Web Vitals certification. The reliable performance gates are shared configuration requests, no repeated absent-endpoint probe, and no roster requests on pagination/warm return. Requests to an optional Executive Summary endpoint may return one expected 404 before the existing summary-composition fallback runs.
