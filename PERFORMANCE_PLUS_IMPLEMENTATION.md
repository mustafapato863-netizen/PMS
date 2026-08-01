# Performance+ First Implementation Release

Date: 2026-08-01
Scope: Safe first release from `PERFORMANCE_PLUS_ROADMAP.md`.

## Implemented

### Frontend

- Added `npm run budget` and `npm run build:ci` to enforce raw/gzip limits for the charts, animation, and Team Dashboard chunks.
- Added component-level lazy loading for `TeamChartsSection` in the Team Dashboard.
- Added a fixed-size, accessible loading skeleton so chart loading does not cause layout shift.

### Backend

- Priority-only Insights no longer runs the planning classification pass because Team Dashboard does not render that context.
- Full Insights retains the existing planning classification and response behavior.
- Added regression coverage proving the priority path skips the unused computation and preserves priority generation.

## Measured results

| Metric | Before | After |
|---|---:|---:|
| Team Dashboard route | 185.67 kB raw / 48.73 kB gzip | 183.88 kB / 48.13 kB |
| Team chart lazy chunk | synchronous | 2.68 kB raw / 1.15 kB gzip |
| Charts chunk | 392.53 kB raw / 112.70 kB gzip (Vite units) | 383.33 KiB / 108.99 KiB measured by the budget script |
| Animation chunk | 132.20 kB raw / 43.28 kB gzip (Vite units) | 129.11 KiB / 41.82 KiB measured by the budget script |

The charts and animation library chunks retain their existing size; the measurable frontend win is that the Team Dashboard route no longer loads the chart module synchronously. The priority classification change is a compute reduction only. No end-to-end latency or SQL reduction is claimed until it is measured against a restarted staging/runtime process.

## Verification

- Backend focused Insights: 19 passed.
- Frontend typecheck: passed.
- Frontend lint: passed.
- Frontend targeted tests: 6 passed.
- Frontend full suite: 55 files / 189 tests passed.
- Production build and bundle budgets: passed.
- Playwright layout/accessibility smoke: 24 passed across Chromium, Firefox, WebKit, and Edge.
- `git diff --check`: passed; only existing line-ending warnings remain.

Full backend regression reached 540 passed and one unrelated date-sensitive failure in `tests/test_report_story_service.py`: its fixture due date is 2026-07-31 while the current environment date is 2026-08-01, so the runtime's `Overdue` result is correct. That test is outside the modified performance paths and was not changed.

## Remaining roadmap work

- Period-scoped Insights loading and real query-count reduction.
- Additive compact Performance summary contract and consumer migration.
- Production Web Vitals, cold-start, pool, and p95/p99 telemetry.
- Async report/import jobs and object-storage outputs.
- Production realtime decision: Supabase Realtime or persistent Socket.IO hosting.
- Staging load profile and canary rollout.
