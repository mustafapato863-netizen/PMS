# Evaluation rule input units — bounded QA lane

Date: 2026-10-10. Worktree: `C:\Users\sghd70204\.codex\worktrees\evaluation-roadmap-closure\PMS_Dashboard`, branch `codex/evaluation-roadmap-closure`. Baseline HEAD: `625abf431ae10659edb93ddb3e879de4ac47c6d8`. No stage, commit, push, merge, deploy, reset, or production write.

This lane is the settings-editor input-unit gap only. It does not close Phase 6, D001–D005, or the monthly-evaluation roadmap.

## What changed

Percent targets and every weight are entered on a 0–100 scale. The save payload still stores fractions: a displayed `65` with unit `%` is stored as `0.65`, and a displayed weight `60` is stored as `0.6`. Scaling applies only when `line.unit` is `%`, `percent`, or `percentage` after trim and case folding. Hours, minutes, counts, currency, and any other explicit unit stay on the printed unit. A missing unit stays on the stored number and is labeled as stored as entered. The KPI name is not used as a unit.

Blank text, unfinished text such as `0.`, and non-finite text stay in the field, keep the previous saved number visible, and block save. An untouched field keeps the same stored number, including a null workbook target. Changing year, month, or scope drops unsaved typing. Approved months and unsupported formulas stay locked. Save, preview, approve, and apply remain separate actions.

Fixed-target mismatch cells use the unit on the matching on-screen rule. A rule with no unit, and a KPI that is not on screen, stay on the stored scale.

`evaluationSettings.ts` is unchanged. Backend schema, scoring math, and capability checks are unchanged.

## Files

| Path | Role |
| --- | --- |
| `Frontend/src/components/settings/evaluationInputUnits.ts` | New conversion, draft commit, and identified-conflict formatting |
| `Frontend/src/components/settings/evaluationInputUnits.test.ts` | New helper coverage |
| `Frontend/src/components/settings/EvaluationSettingsPanel.tsx` | Draft text inputs, labels, help, locks, conflict units |
| `Frontend/src/components/settings/EvaluationSettingsPanel.test.tsx` | Percentage display and exact fraction storage |
| `docs/guides/monthly-evaluation-admin.md` | Operator description of the percent UI and fractional API |
| `docs/qa/evaluation-input-units-2026-10-10.md` | This evidence note |

Tracked diff at the time of this note:

```
Frontend/src/components/settings/EvaluationSettingsPanel.test.tsx | 166 ++++++++++++++++++---
Frontend/src/components/settings/EvaluationSettingsPanel.tsx      | 143 +++++++++++++++---
docs/guides/monthly-evaluation-admin.md                           |  12 +-
3 files changed, 276 insertions(+), 45 deletions(-)
```

The two helper files are untracked. `graphify-out/` was regenerated after the edit and is not part of the feature. Graphify also wrote a backup under `graphify-out/2026-10-10/`.

## Commands and results

Working directory for the frontend commands: `Frontend`. Dependencies were already installed. Nothing was installed for this lane.

1. Focused Vitest, exit 0.

```
.\node_modules\.bin\vitest.cmd run src/components/settings/evaluationInputUnits.test.ts src/components/settings/EvaluationSettingsPanel.test.tsx src/components/settings/evaluationSettings.test.ts --reporter=verbose
```

Vitest 4.1.11. Test files 3 passed. Tests 31 passed. Start 01:49:18. Duration 13.94s (transform 1.84s, setup 3.35s, import 2.84s, tests 5.80s, environment 12.71s). The only extra output was Node’s `NO_COLOR` / `FORCE_COLOR` warning.

Helper cases included stored `0.65` → `65`, UI `70` → `0.7`, stored `0.001` → `0.1`, weight `0.6` → `60`, UI `50` → `0.5`, zero, hours `2.5` unchanged, count `65` unchanged when the label says “Rework percentage”, unknown and blank units unchanged, blank and non-finite text rejected, and an untouched `0.1 + 0.2` weight plus a null workbook target kept by object identity. Component cases included the same mixed save (`70` stored as `0.7`, count weight `50` stored as `0.5`), blank and `0.` blocking PATCH while the saved `55%` stays visible, month change dropping `0.`, conflict formatting (`60%` / `55%`, `2.5 hours`, and raw notes for a missing unit and an unlisted KPI), Admin-only hiding of the editors for Manager and Performance Team, and a disabled approved-month target `55` with weight `100`.

2. ESLint on the six settings files, exit 0, no findings. Same `NO_COLOR` warning.

```
.\node_modules\.bin\eslint.cmd src/components/settings/EvaluationSettingsPanel.tsx src/components/settings/evaluationInputUnits.ts src/components/settings/evaluationInputUnits.test.ts src/components/settings/EvaluationSettingsPanel.test.tsx src/components/settings/evaluationSettings.ts src/components/settings/evaluationSettings.test.ts
```

3. Typecheck, exit 0, no diagnostics, 36.81s.

```
.\node_modules\.bin\tsc.cmd -b --pretty false
```

4. Production build and bundle budget, exit 0.

```
npm run build:ci
```

Vite 8.1.4 transformed 3396 modules and finished in 2.11s. `dist/assets/index-B2OsOm5q.js` is 512.58 kB (gzip 153.66 kB). Vite printed its existing warning that some chunks are larger than 500 kB. `node scripts/check-bundle-budget.mjs` then printed:

```
BarChart-BNfMU6A1.js: 16.20 kB raw / 5.64 kB gzip
CartesianChart-B-Rrz6PM.js: 324.81 kB raw / 95.16 kB gzip
GradeDistributionChart-CXe_FhZ8.js: 2.65 kB raw / 1.16 kB gzip
LineChart-VWvPA9IZ.js: 21.29 kB raw / 6.25 kB gzip
charts runtime aggregate: 364.95 kB raw / 108.21 kB gzip
animation-BQ36ZQFk.js: 129.19 kB raw / 41.86 kB gzip
TeamDashboardView-DfTNudmu.js: 139.07 kB raw / 35.59 kB gzip
Bundle budgets passed.
```

5. AST graph update from the worktree root, exit 0, 146.72s.

```
graphify update .
```

Result: 847 files, 9669 nodes, 26331 edges, 433 communities. Report built from commit `625abf43`. Warnings: 21 source files produced zero nodes (`settings.json`, `coding.json`, `csr.json`, `inbound.json`, `inbound_uae.json`, and 16 more); 1 `.sql` file was skipped because `tree_sitter_sql` is not installed. That dependency was not installed. Community labels were not refreshed with an LLM.

## Not run

- Browser or mobile viewport pass. No dev server was started.
- Full frontend Vitest suite, backend pytest, PostgreSQL, JWT login, and all-team UAT.
- A separate test that changing scope or year drops a draft. Both use the same selection reset as the tested month change.
- Per-KPI proof subtitles in `monthlyCorrection.ts`. Those rows have no unit, and that file is outside this lane, so actual, workbook target, applied target, weight, achievement, and contribution stay on the stored numbers.

## Residual risk

### Independent reviewer verification

The combined-candidate real JWT browser test passed percentage entry65/60 to70/50/20, exact fractional storage.7/.5/.2, blank-input Save blocking and no result/source mutation during Save. Settings field bounds, document overflow, keyboard traversal and no page errors passed at320/375/640/746/768/1024/1440 in both light and dark mode. Screenshots settings-320-dark.png and settings-746-light.png were visually inspected; all screenshots are under the owned reviewer-closure-unit-evidence-20261010 output directory.

Two harness issues were corrected rather than treated as product waivers: responsive media-query rendering now waits for the final no-overflow condition up to three seconds (persistent overflow still fails), and the known API-approved fixture now waits for Revise this month instead of skipping it when the asynchronous DOM is temporarily empty. The earlier immediate-dark320 overflow observation and disabled-approved-input failure are retained in the task checkpoint. The repeated browser gate passed.

Visual inspection exposed a real label mismatch: an admitted historical month showed the current catalog's blocked suffix while its actual editor was correctly admitted. A new exact-August versus blocked-September regression failed, then passed after the selected option used the selected period's authoritative readiness. This is display-only and does not widen backend admission. The final focused frontend gate passed36cases; the full final frontend passed750cases/100files in239.28seconds with two workers and unchanged timeouts. Typecheck, changed-file ESLint and build:ci/budget repeated successfully after the refinement.

Actual JWT apply/rollback across six API consumer families and Function/Employee DOM also passed on the combined candidate; July and raw source remained unchanged. These checks used anonymous disposable fixtures, not production data or private workbook edits.

The editor does not clamp. `110` is stored as `1.1` and `-5` as `-0.05`. Scientific notation and thousands separators are rejected. A conflict whose rule is absent from the screen is left raw even if the number looks like a fraction. If the API omits `unit`, this UI does not invent `%`.

Other dirty files already in this worktree were left untouched: `Backend/api/routers/evaluation_settings.py`, `Backend/services/evaluation/workflow.py`, `Backend/tests/test_monthly_evaluation.py`, `Backend/tests/test_evaluation_optimistic_http.py`, `Backend/tests/test_evaluation_reads_validation.py`, `docs/plans/monthly-evaluation-settings-plan.md`, and `docs/plans/monthly-evaluation/closure-matrix-2026-10-10.md`.
