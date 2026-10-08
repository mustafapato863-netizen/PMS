# Phase 1A independent review — rework required

Run 1 completed without commits. Its reported passing suites are necessary but insufficient for acceptance. Phase 1A is not yet accepted.

Independent PostgreSQL 18 probes against a separate synthetic review database, fully rolled back, proved:

1. A named unique constraint on `(team_id_extra, version_number)` was accepted as `(team_id, version_number)` by substring matching. Two rows with the same actual team and version could then be inserted.
2. With `search_path=shadow_review,public`, inspection checked public but unqualified DDL created the groundwork in shadow_review. Upgrade reported success while public remained unrepaired.

Required corrections: exact catalog identities, consistent schema qualification including referenced FK schema, rejection of incompatible named indexes, explicit unsupported partial-shape errors, and real PostgreSQL negative regressions. Tests must allow a later additive child migration rather than permanently freezing this revision as latest head.

Initial independent focused suite: 70 passed, 7 skipped (six opt-in PostgreSQL cases and one existing local-dataset skip). This is not the PostgreSQL acceptance gate. Run 1 reported 1070 passed/8 skipped for the full suite in the isolated worktree; the external Marketing acceptance workbook was absent, so its known failure was not exercised.

No main merge, production migration, or feature activation is approved by this review. Existing raw, KPI and management evidence must remain unchanged through all corrections and round trips.

## Run 2 review

Run 2 completed exit 0. Independent PostgreSQL probes confirm the original unique/schema issues, partial-index drift, wrong referenced schema and missing required columns now reject or repair as intended. Reported suites: foundation 19 passed on each PostgreSQL 18/16 target; isolated full backend 1070 passed/15 skipped. No acceptance yet.

Two additional blocking probes still reproduce:

- CHECK normalization discards arithmetic grouping, equating `year * (12 + month)` with `year * 12 + month`. A range ending December 2025 before its January 2026 start was inserted after upgrade accepted the altered constraint.
- The expected record FK marked `NOT VALID` over an existing orphan version link is accepted. Checking names/columns/delete action is insufficient when existing data has never been validated.

Both probes use a separate synthetic database and fully roll back. Require preserved CHECK semantics and validated foreign-key identity, with negative regressions preserving incompatible data/schema/head. No silent validation, clearing or rewriting of old evidence. Same-session bounded rework is required before commit/PR.

## Final independent verdict after run 3

The six reviewed detection defects are corrected. Separate rolled-back probes pass on PostgreSQL 18 and 16. Codex independently ran the complete foundation file: 22 passed on each server (134.61s / 136.13s), covering upgrade, preservation, retention-first downgrade/re-upgrade, ORM bootstrap and negative drifts.

Full backend: 1070 passed, 1 failed, 17 skipped, 250.50s. The sole failure is the unchanged real Marketing workbook assertion, 131 rows versus 68 expected; the same exact case fails on untouched primary main. Implementer skip output did not prove workbook absence; evidence was corrected to distinguish skipped versus independently executed verification.

Accept this bounded schema slice for a separate draft PR, subject to CI. Phase 1, Marketing golden acceptance and monthly settings functionality remain incomplete. No main merge, production migration or feature activation.
