# Codex review — Phase 0 (in progress)

The implementer completed the bounded source-audit/test slice after rework. This review accepts the documentation and synthetic baseline for a **draft PR**, not full Phase 0/scoring/production acceptance or main merge.

## Verification so far

- Read all five new characterization test files before running them; synthetic scoring, mocked repositories and disposable in-memory management DB. No existing tests were weakened or changed at this checkpoint.
- Independently ran the five new test files with APP_ENV=test and a pinned disposable connection: **20 passed**, 1.99s.
- Independently reran relevant existing scope/config/cache tests: **20 passed** (details in orchestrator-migration-preflight.md).
- Independently inspected actual LOCAL schema/catalog with a read-only transaction and no people/grant payload exports (orchestrator-local-schema-inventory.md).
- Verified supported fresh ORM bootstrap separately from failing direct/historical SQL migration paths (orchestrator-migration-preflight.md).

## Rework required before acceptance

1. Characterization must protect calculation outputs, not permanently require missing architecture. In test_evaluation_baseline_history.py, asserting that configuration_version_id is absent from PerformanceRecord will fail the required Phase 1 ORM mapping. Similarly assertions that public functions have no month/period parameter unnecessarily forbid compatible signature evolution. Move these architectural observations to the audit report; retain numerical/persistence/scoping behavioral assertions. Do not remove meaningful scoring checks or hide known defects.
2. Incorporate authoritative D-001 (Admin-only all lifecycle stages) from approved-decisions.md; the plan's Performance Team draft/preview proposal was rejected by the user.
3. Incorporate independent LOCAL runtime evidence: 16 active employee sources + 7 real DB-only management sources, version groundwork present in local DB but absent from fresh ORM bootstrap, PostgreSQL 18.4, existing version FK/unique and partition constraints. Do not continue labeling this specific local metadata unknown. Production remains uninspected, actual-data golden snapshots remain separate.
4. Distinguish supported bootstrap success from migration-chain failures and avoid saying startup is broken based only on direct empty upgrade. Phase 1 must reconcile schema drift idempotently, without touching current databases.

Full backend suite is being run independently with DATABASE_URL=sqlite:///:memory: and APP_ENV=test. Record its actual final outcome when available; it does not certify PostgreSQL migration semantics.

Full local run finished: **1064 passed, 1 failed, 1 skipped**, 239.20s. Failure is the existing local acceptance-workbook test tests/test_marketing_import.py::test_real_marketing_workbook_imports_with_incomplete_rows_excluded: current external workbook yields 131 total rows; assertion expects 68. The test already excludes itself when CI=true or its external workbook is absent. It was not changed or skipped by this work. Reproducing on untouched primary main in a fresh process is the next check before calling it pre-existing.

Untouched primary main reproduction confirmed **the identical failure**, 131 versus 68, in a fresh isolated process (3.87s). This is an existing out-of-repository acceptance-workbook drift, not caused by the new tests. Keep it visible as an unresolved local acceptance issue. Do not alter the expected count to 131 without establishing the workbook's intended golden input and score expectations; do not present a CI-only run as passing this local acceptance case.

## Final bounded review

- Grok continuation finished, exit 0, correctly reporting partial Phase 0. Read the full audit and regenerated inventory, all five tests and three synthetic fixtures. No application source, old tests, permissions or live DB changes.
- Rework resolved architecture-absence/signature locks; scoring/grant/history numerical checks retained. Independently reran the exact wider targeted set: **64 passed, 1 existing skipped local-dataset case, 7 warnings**, 2.72s. Full-suite result above remains visible; not all local acceptance gates passed.
- Corrected audit/inventory reversal of OP Dubai name versus db_name, corrected Marketing scoring-weight wording, and incorporated later zero pinned-version count. Flagged person scope as preservation of existing management scope, not new overrides. Flagged FK deletion-history risk as a blocking approval/activation concern, not a waived invariant.
- JSON inventory parses and covers 16 tracked definitions. Source graph refresh completed (8680 nodes); existing zero-node/optional SQL-parser warnings remain. Generated graph is ignored, not part of the PR.
- Accept only off-main draft publication. Later lifecycle/scoring work must honor D-001, explicit unsupported recomputation, no automatic history changes, and the remaining real-golden/product/schema gates. No feature activation/deployment is approved by these results.
