# Local QA and performance results — 2026-10-08

Implemented locally; no commit, push, merge, deployment, production test, or business-data update.

## Results

- 23 real Chromium browser checks passed using Admin and an existing Dubai Branch Director account.
- 568 frontend tests passed across 82 test files.
- Type checking, lint, production build, bundle budgets, and whitespace checks passed.
- Backend standard test configuration: 949 passed, 1 skipped. This run explicitly disabled the scoped API default for legacy contract tests and set `CI=true`; tests of scoped endpoints configure their own settings. The running local backend was not reconfigured and its scoped API remained enabled for the browser tests.
- Before aligning the test environment, the full backend run had 948 passes and two failures: a legacy employee-history contract exercised the enabled authenticated scoped route, and the external Marketing workbook did not match its historical acceptance assertions. The legacy test passed when run with its intended disabled-feature configuration.

## Measured changes

The same repeated Executive → RCM team → Executive navigation scenario produced **96 full-record requests before the team-history optimization, versus 6 afterward** (93.75% fewer). The six reads are now restricted to RCM and reused across consumers/remounts. Request counts, rather than development-server timing, are the reliable improvement here.

Sidebar configuration reads decreased from four to two on first load. The optional, currently absent Executive Summary endpoint is probed once per authenticated scope within five minutes instead of on each filter change. Only HTTP 404 is cached; permission/network/server failures are not recorded as a missing capability.

The Executive employee roster still shows eight employees per page, caches bounded initial batches, and makes no new roster requests on Next/Previous or a warm return. New unit tests verify isolation across team/user/grant changes, disabled consumers, and explicit refresh after data updates.

Browser checks also cover actual team roster loading, inline all-teams expansion, Coding → RCM filter cascading, clear filters, all three level choices, 390/768/1440px layouts, Escape behavior, keyboard-operated trend values using `%`, RCM Function Summary navigation, logout, locked Dubai scope, hidden restricted workspaces, unavailable Admin settings, and empty/denied out-of-scope branch reads.

## Remaining limitations / not release-certified

- **Marketing workbook acceptance is not passed.** The local `D:\Trend\PMS_Trend_All.xlsx` produces 131 rows while the historical test expects 68. This external-file test is intentionally skipped by the existing CI condition. No baseline expectations or workbook contents were changed; a reviewed acceptance baseline is still needed.
- Current function definitions expose Call Center, RCM, and Marketing. CSR/Sales/Pharmacy remain standalone team choices without their own function choices. Cascading was verified for the configured hierarchy, not certified for those standalone teams; this domain change was not folded into the performance work.
- RCM aggregate team-action requests return HTTP 404 in the current local backend. Browser navigation/rosters work, but aggregate action API support was not changed or certified here.
- The existing build warning for a main chunk just over 500 kB remains, although configured bundle budgets passed. Browser measurements are from local Vite development mode, not production load-time guarantees or a complete RLS/security certification.
- The code knowledge graph was refreshed without an external AI call (8,504 nodes). Graph coverage warnings remain for JSON configuration files producing no nodes and a SQL file lacking the optional SQL parser; this does not affect runtime tests, but the graph is not a complete configuration/schema map.

Re-run instructions: [README](./README.md). Detailed local request evidence is generated under ignored `e2e/artifacts/`; reports omit credentials, employee rows, authentication payloads, and pagination cursors.
