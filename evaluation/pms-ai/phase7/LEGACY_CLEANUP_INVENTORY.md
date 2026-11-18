# Phase 7 Legacy Evaluation & Provider Cleanup Inventory (#102)

This inventory documents the Phase 7 surgical cleanup of unreferenced legacy evaluation scripts and the intentional retention of active or compatibility-guarded modules.

## Removed Legacy Scripts (Unreferenced)

| File Removed | Reason for Removal | Verification |
|---|---|---|
| `Backend/services/ai/evaluate_full_coverage_holdout.py` | Obsolete Phase 6 ad-hoc script inside `Backend/services/ai/` that imported `pytest`, mutated `os.environ["DATABASE_URL"]` at import time, referenced external `D:/PMS_AI/pms_ai_golden_50.py`, and scored answers via naive substring checks. Zero production/test imports (`rg` confirmed). Superseded by `evaluation/pms-ai/phase7/run_comparative_eval.py`. | Removed via `git rm`; AST/import gate in `Backend/tests/test_ai_phase7_eval_gates.py` enforces no `Backend/services/ai/*.py` imports `pytest` or mutates `DATABASE_URL`. |
| `Backend/scripts/evaluate_call_center_dialogue.py` | Obsolete ad-hoc script that imported `pytest`, mutated `DATABASE_URL` at import time, and evaluated 25 hard-coded synthetic Call Center turns via substring checks. Zero production/test imports (`rg` confirmed). Superseded by Phase 0/4/7 runners. | Removed via `git rm`; verified absent and full backend suite green. |
| `Backend/services/ai/classifier.py` | Rejected PR 6 offline TF-IDF intent classifier (`LocalIntentClassifier`). Superseded by model-led routing and `local_model_router.suggest_intent`. | Removed in Phase 6 cleanup; `AiRuntimeConfig.classifier_mode` pinned unconditionally to `"off"`. |
| `Backend/scripts/evaluate_ai_classifier.py` | Offline evaluator for the retired TF-IDF `LocalIntentClassifier`. | Removed in Phase 6 cleanup; verified absent with zero runtime imports. |
| `Backend/scripts/evaluate_pms_ai_improvements.py` | Legacy PR improvement evaluator overlapping with `Backend/scripts/run_unseen_eval.py` and Phase 5 validation runners. | Removed in Phase 6 cleanup; consolidated into `run_unseen_eval.py` and Phase 5 runners. |
| `Backend/requirements-ai-eval.txt` | Unused `scikit-learn>=1.5.0` manifest solely for the retired offline classifier. | Removed in Phase 6 cleanup along with `.dockerignore` references. |

## Intentionally Retained Modules

| File / Symbol Retained | Reason for Retention |
|---|---|
| `OpenAIProviderAdapter` (410 stub in `Backend/services/ai/provider_engine.py`) | Compatibility-guarded deprecated stub (`execute` always raises `ProviderClientError(..., http_code=410)` with zero network I/O). Explicitly tested by `Backend/tests/test_ai_provider_engine.py`. |
| `Backend/services/ai/providers.py` | Active provider configuration and Gemini/fallback helper module imported by AI routers and tests. |
| `Backend/scripts/run_unseen_eval.py` | Authoritative regression & unseen evaluation runner (immutable Phase 5 SHA-256 preserved). |
| `Backend/scripts/certify_scopes_and_benchmark.py` | Standalone scope certification and benchmark utility script. |
