# CI Green Gate & Pre-Push Verification Rules

Every push or pull request to `main` runs **four CI jobs** defined in `.github/workflows/ci.yml`:
1. `frontend` (`lint`, `typecheck`, `test`, `build:ci`)
2. `coverage-manifest` (`evaluation/pms-ai/phase2/tests/test_coverage_manifest.py`)
3. `backend` (full `pytest -q`, including Phase 0/1/2 manifest & inventory parity checks)
4. `containers` (shell syntax, Compose contract validation, production image builds)

To guarantee CI stays **100% green** and never repeats past failures, ALWAYS follow these rules before committing or pushing:

---

## Rule 1 — Always Use `npm run typecheck`, NEVER Bare `npx tsc --noEmit`
- `Frontend/tsconfig.json` is a TypeScript Project References solution file (`"files": []`).
- Running `npx tsc --noEmit` validates ZERO source or test files and produces false positives!
- **Mandatory Frontend Gate** (from `Frontend/`):
  ```powershell
  npm run lint
  npm run typecheck
  npm test
  npm run build:ci
  ```
- Never construct partial mock `AgentRecord` or `MonthlyOverviewData` objects with invented properties (such as `year` inside `identity`, `grade_class`, `aht_seconds`, or `companyPerformance`)—always verify against `Frontend/src/types.ts` and `Frontend/src/features/monthlyPresentation/monthlyOverviewData.ts`.

---

## Rule 2 — Regenerate Phase 0 Test Inventory Whenever AI Tests Change
- `Backend/tests/test_pms_ai_phase1_baseline_links.py::test_test_type_inventory_matches_the_script` fails in CI whenever ANY file matching:
  - `Backend/tests/test_ai_*.py`
  - `Backend/tests/test_pms_ai_phase0_*.py`
  - `Backend/tests/test_local_*.py`
  - `Frontend/src/components/ai/**/*.test.tsx`
  - `Frontend/src/features/ai/**/*.test.ts`
  - `Frontend/src/pages/PmsAiWorkspaceView.test.tsx`
  is added, removed, or changes its test case count or mock/live labels.
- **Mandatory Fix Before Commit** (from repo root):
  ```powershell
  python evaluation/pms-ai/phase0/inventory_test_types.py
  ```
  Then verify:
  ```powershell
  cd Backend; python -m pytest tests/test_pms_ai_phase1_baseline_links.py -q
  ```
  Stage the updated `evaluation/pms-ai/phase0/test_type_inventory.json` and `evaluation/pms-ai/phase0/TEST_TYPE_INVENTORY.md` in the same commit.

---

## Rule 3 — Regenerate Phase 2 Coverage Manifest Whenever Catalog, Team Configs, or AI Docs Change
- The `coverage-manifest` CI job runs `evaluation/pms-ai/phase2/tests/test_coverage_manifest.py::test_committed_outputs_match_the_generator`.
- Whenever `Backend/config/teams/*.json`, `Backend/services/ai/catalog.py`, `Backend/services/ai/coverage_manifest.py`, `Backend/services/ai/config.py`, or `docs/plans/pms-ai-evidence-first/*` changes, regenerate the manifest before committing (from repo root):
  ```powershell
  python evaluation/pms-ai/phase2/generate_coverage_manifest.py
  python -m pytest -q evaluation/pms-ai/phase2/tests/test_coverage_manifest.py
  cd Backend; python -m pytest tests/test_ai_phase2_reconciliation.py -q
  ```
  Stage the updated `evaluation/pms-ai/phase2/coverage_manifest.json`, `coverage_matrix.csv`, and `coverage_report.md` in the same commit.

---

## Rule 4 — Verify Backend Manifest & Changed Test Suites Together
- Never push Backend AI or config changes after running only a subset of unit tests without ALSO running:
  1. All tests touching modified modules (and `Backend/tests/test_ai_phase3_tool_contracts.py` whenever `AUTHORIZED_MODEL_LED_TOOLS` changes)
  2. `Backend/tests/test_pms_ai_phase1_baseline_links.py`
  3. `evaluation/pms-ai/phase2/tests/test_coverage_manifest.py`
- If modifying `DevOps/scripts/*.sh`, `docker-compose.yml`, or `compose.production.yml`, also run `python -m unittest discover -s scripts -p 'test_validate_deployment_compose.py'`.

---

## Rule 5 — Check GitHub Actions After Every Push
- If `gh` CLI is available, confirm the triggered CI workflow finishes green—never leave a known red `main` build unresolved.
