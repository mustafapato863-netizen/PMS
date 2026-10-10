# Evaluation draft optimistic edits — bounded QA lane

Date: 2026-10-10. Worktree: `C:\Users\sghd70204\.codex\worktrees\evaluation-roadmap-closure\PMS_Dashboard`, branch `codex/evaluation-roadmap-closure`. No stage, commit, push, merge, deploy, reset, or production write.

This lane adds the settings-screen counterpart to the draft rules-checksum contract already present on this branch. It does not close the monthly-evaluation roadmap, Phase 6, or Phase 7.

## Contract checked

The serializer field is `checksum`. That is the rules checksum stored on `config_checksum`. `source_checksum` is lineage only and is not sent as the edit token.

HTTP `PATCH /drafts/{version_id}` passes `require_precondition=True`. Pydantic still accepts a body with `expected_checksum` omitted, so a caller who fails the persisted Admin check can receive 403 before the precondition is judged. An authenticated HTTP edit does not skip a missing checksum: that response is 409 `draft_precondition_required` and the draft is unchanged. A stale checksum is 409 `stale_draft`. The comparison uses the row loaded with `populate_existing()` after the existing lock request, and it happens before lines change or preview evidence is cleared. The same checksum with unchanged lines is accepted and leaves the stored lines and checksum in place.

The role string on the request is not the authority. `get_current_user_scope` loads the persisted user, and `_require_admin` requires that user's role to be Admin and `is_active` to be true before version lookup. A Performance Team user, a Performance Team user presented as Admin, and a disabled Admin all receive 403. Those responses do not use `not_found`, `stale_draft`, or `draft_precondition_required`.

`EvaluationWorkflow.edit_draft` still defaults `require_precondition` to false. Internal callers that are not the HTTP edit keep that path. If they pass a checksum, it is checked. This lane did not change that default.

The screen captures the version id, rules checksum, scope, year, month, and line units when a text, direction, or source edit starts. A later period refetch does not replace that token or reinterpret a typed number under a new unit. Save posts `expected_checksum` to the captured version only. A refetch that changes the open version disables save and offers **Reload draft** and **Discard edits** instead of writing the other version. A 409 leaves the typed text in place, does not retry, and does not replace the refreshed period cache with the rejected body. Selection changes, a successful save, and discard drop the token and the typed text. A blank or whitespace checksum disables save and is not posted. A revise response that omits `checksum` does not keep the previous version's checksum.

Percent entry is unchanged: `70` on a `%` target is stored as `0.7`, a count weight `50` is stored as `0.5`, and an untouched `0.1 + 0.2` weight stays that number.

## Backend review

The router and workflow files were already dirty with the checksum contract. This lane did not edit them. Re-running the HTTP file reproduced no defect: stale second Admin, missing token, spoofed Admin, non-Admin, disabled Admin, and an unchanged checksum all matched the contract above. The stale case still keeps the newer snapshot, checksum, and stored preview proof.

## Files this lane wrote

| Path | Role |
| --- | --- |
| `Frontend/src/components/settings/EvaluationSettingsPanel.tsx` | Capture the base checksum, version, and lines; send that token; block a missing token or a different version |
| `Frontend/src/components/settings/EvaluationSettingsPanel.test.tsx` | Fraction assertions kept; refresh, 409, version change, empty checksum, and cross-month cases added |
| `Backend/tests/test_evaluation_optimistic_http.py` | Existing two-Admin HTTP cases kept; non-Admin, disabled Admin, and unchanged-checksum cases added |
| `docs/guides/monthly-evaluation-admin.md` | Operator note for two-admin edits and the HTTP versus internal difference |
| `docs/qa/evaluation-optimistic-edits-2026-10-10.md` | This evidence note |

`graphify-out/` was regenerated after the edit. It is not part of the feature.

Left untouched: `Backend/api/routers/evaluation_settings.py`, `Backend/services/evaluation/workflow.py`, `Backend/tests/test_monthly_evaluation.py`, `Backend/tests/test_evaluation_reads_validation.py`, `Frontend/src/components/settings/evaluationInputUnits.ts`, `Frontend/src/components/settings/evaluationInputUnits.test.ts`, `docs/plans/monthly-evaluation-settings-plan.md`, `docs/plans/monthly-evaluation/closure-matrix-2026-10-10.md`, `docs/qa/evaluation-input-units-2026-10-10.md`, and the Insights branch.

## Commands and results

Environment for pytest, set before Python started: `APP_ENV=test`, `DATABASE_URL=sqlite:///:memory:`, `REDIS_URL` empty, `CI` removed when it was present. The fixture uses in-memory SQLite, synthetic users at `example.invalid`, and the catalog's Coding scope label. It does not open a production database or a private workbook.

1. Focused HTTP pytest, exit 0. 6 passed in 9.28s. Eight warnings, all existing Starlette and Pydantic deprecations in import paths, not assertion failures.

```
python -m pytest tests/test_evaluation_optimistic_http.py -q --tb=short
```

2. Focused Vitest, exit 0. Vitest 4.1.11. 3 files, 35 tests passed. Started 02:13:35. Duration 7.18s. Node printed its existing `NO_COLOR` / `FORCE_COLOR` warning.

```
.\node_modules\.bin\vitest.cmd run src/components/settings/evaluationInputUnits.test.ts src/components/settings/EvaluationSettingsPanel.test.tsx src/components/settings/evaluationSettings.test.ts --reporter=verbose
```

The fraction cases still expect `70` stored as `0.7`, count weight `50` stored as `0.5`, hours `2.5`, and the untouched `0.1 + 0.2` weight. New cases cover a refetch during a dirty edit (typed `70` stays on the `%` scale, `expected_checksum` stays `sum-draft`, one 409, no second write), a changed version id (no PATCH until discard, then `sum-other` goes only to `draft-other`), a whitespace checksum (no PATCH), and a July token that is not sent for August. A revise body with no `checksum` does not send the approved checksum.

3. ESLint on the panel and its test, exit 0, no findings. Same `NO_COLOR` warning.

```
.\node_modules\.bin\eslint.cmd src/components/settings/EvaluationSettingsPanel.tsx src/components/settings/EvaluationSettingsPanel.test.tsx
```

4. Typecheck, exit 0, no diagnostics, 25.46s.

```
.\node_modules\.bin\tsc.cmd -b --pretty false
```

5. Production build and bundle budget, exit 0.

```
npm run build:ci
```

Vite 8.1.4 transformed 3396 modules and finished in 2.82s. `dist/assets/index-GYEiDAse.js` is 512.58 kB (gzip 153.66 kB). Vite printed its existing warning that some chunks are larger than 500 kB. `node scripts/check-bundle-budget.mjs` printed the same budget totals as the input-unit lane (`charts runtime aggregate: 364.95 kB raw / 108.21 kB gzip`) and `Bundle budgets passed.`

6. AST graph update from the worktree root, exit 0, 59.48s.

```
graphify update .
```

Result: 9694 nodes, 26371 edges, 428 communities. Warnings: 21 source files produced zero nodes; `tree_sitter_sql` is not installed, so one `.sql` file was skipped. That dependency was not installed. Community labels were not refreshed with an LLM.

## Not run

- A desktop or mobile browser pass. No dev server was started. The conflict, reload, discard, and fraction behavior was exercised in the component tests.
- The full frontend Vitest suite, the full backend suite, PostgreSQL row locks, JWT login, and all-team UAT.
- Marketing dashboard tests. They were not skipped with a waiver; they were outside this focused run.

## Residual risk

### Independent reviewer follow-up

The first actual two-client JWT browser run exposed an additional UX gap: after the server rejected the stale checksum with409, Save draft remained enabled. A new assertion reproduced the same defect in the component test. The reviewer added both an event-handler guard and a disabled Save state until explicit reload/discard; the three focused frontend files then passed35tests in8.05seconds.

The repeated browser check passed using two independent Chromium contexts against the owned anonymous loopback fixture: the first client's PATCH returned200, the stale second client's PATCH returned409 with its original frozen checksum, unsaved75 remained visible, Save was disabled, and explicit Reload draft displayed the committed70. Source performance records and stored results remained unchanged. Evidence: reviewer-closure-two-clients-evidence-20261010/proof.json and stale-client.png in the task's local tmp directory. No production or user database was used.

The reviewer independently ran the PostgreSQL16/18 suite after adding the stale second-Admin ORM identity-map test:28passed, repeated after the portable UUID model mapping with28passed in61.61seconds. This checks fresh checksum loading under the PostgreSQL lock and preservation of preview proof, not general production load or all-role UAT.

SQLite cannot take the PostgreSQL row lock. The HTTP tests use one connection and `populate_existing()`, so they see a committed checksum, but they do not prove the database lock under two concurrent Postgres transactions. The screen cannot save a draft whose payload has no `checksum`; an operator reloads the month to obtain one. Internal workflow callers can still edit without a browser token, which is the documented split from the HTTP edit.
