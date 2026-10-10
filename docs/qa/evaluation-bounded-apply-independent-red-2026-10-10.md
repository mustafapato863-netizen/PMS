# Phase7B independent rejection checkpoint

Date:10October2026. Candidate isolated at `evaluation-bounded-apply`, based on accepted `6a90e819084c27f7b60934022adefb1908c77e80`. It is not integrated or activated. Initial highest-model delegate reached its55minute watchdog05:26UTC; reviewer verified the writer tree stopped before testing.

## Observed gates

- Candidate's21normal tests passed,9warnings,43.96s. Observed100/1000-row peaks2.70/5.91MB; employeeSELECTs2/60 and recordSELECTs3/70. Bounded memory does not establish bounded total work: each staged page scans the full cohort.
- Independent anonymous SQLite contract:8passed,7failed,9.79s. Primary `tmp/reviewer-bounded-contract-20261010.py` and adjacentJUnitXML retained unchanged.
- Independent native two-connection overlap:2failed,9.34s on PostgreSQL16and18. Primary `tmp/reviewer-bounded-lock-pg-20261010.py` and adjacentJUnitXML retained. Only reviewed disposable loopback55432/55433 databases reset; no production/private data.

## Proven blocking defects

1. A99row page executes99 stage-existence queries;100row pages execute100. The independent<=3stageSELECT/page assertion rejects the N+1 implementation.
2. Observed header lock sequence is job→control→scope instead of accepted job→scope→control→records. More importantly, existing capture holds its outer team fence before requesting the existing control, while concurrent stage holds the job/control before requesting that team. Both native versions return actual `psycopg2.errors.DeadlockDetected` in the controlled overlap. This is not a flaky timeout assertion.
3. Adapter-level verified readback accepts a parent revision ID different from `promoted_revision_id`, and accepts a changed prior manifest hash. Immutable database guards were not disabled and no forged production row was written by these probes. A known stage hash is not sufficient parent or before/after-pair verification.

Narrow rework requests:consistent lock hierarchy including upload/legacy rollback interaction; bounded existing-stage batch reads preserving conflicting replay; complete revision/control/scope/month/version/epoch/pair binding; hoisted rules/config and less repeated per-KPI evidence serialization. Final full source/permission/drift checks must not be removed to claim faster operation. Independent assertions may not be edited or skipped.

Resume of the old Grok session hung during initialization with zero events; only that verified process tree was stopped, partials preserved. Fresh highest-model `grok-4.7/xhigh` rework started05:34UTC in the same isolated checkout. No simultaneous edits by reviewer. Native rework gates run only after the writer stops.

These failures do not invalidate the separately accepted consumer/foundation closure. Public routes and three existing worker job kinds remain unchanged. Phase7Cworker/retry/cancel and7DUI remain unimplemented; no whole-roadmap or release-green claim.
