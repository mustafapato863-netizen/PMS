# PMS AI Local Intent Classifier Evaluation Report (PR 6)

## 1. Executive Summary & Promotion Decision

- **Decision**: **`DO_NOT_PROMOTE_KEEP_HYBRID_RULES`** (`AI_CLASSIFIER_MODE=off`)
- **Runtime Dependency (`scikit-learn`)**: **Not added** to `Backend/requirements.txt` (preserving a minimal production dependency footprint per Phase 6 of `docs/plans/pms-ai-chatbot-implementation-plan.md`).
- **Why**:
  1. `HybridQueryRouter` (deterministic local rules + catalog entity resolution + follow-up context inheritance) already achieves **100.0% exact outcome, intent, and filter match** across all **126 reviewed English questions** (`57/57` `train`, `22/22` `val`, `47/47` `test`) with **0 external provider calls**.
  2. When calibrated on `val` (`confidence_threshold = 0.35`), the local TF-IDF + L2 multinomial logistic classifier achieves **100.0% precision on accepted local requests** (`14/14` on `test`, passing the `>= 99.0%` precision gate), but abstains on **33/47 (`70.2%`)** of held-out `test` questions and achieves **0.0% provider call reduction** compared to `HybridQueryRouter` (failing the `>= 20.0%` provider call reduction gate).
  3. Lowering the threshold to `0.25` increases local acceptance to `23/47` (`48.9%`), but drops accepted precision on `test` to **87.0% (`20/23`)**, failing the `>= 99.0%` precision gate because structural intents (`compare_periods` with two months, short follow-ups inheriting `last_confirmed_query`, and `actual_vs_target` vs `current_value`) depend on parsed structural entities rather than surface n-grams.

---

## 2. Dataset & Paraphrase-Grouped Split Integrity

- **Fixture**: [`Backend/tests/fixtures/ai_english_questions.json`](file:///D:/Projects/PMS_Dashboard/Backend/tests/fixtures/ai_english_questions.json)
- **Total Reviewed English Questions**: **126** across **61 paraphrase groups** (`grp_01` – `grp_55`)
- **Grouped Split Distribution**:
  - `train`: **57 questions** across **27 paraphrase groups**
  - `val`: **22 questions** across **11 paraphrase groups**
  - `test`: **47 questions** across **23 paraphrase groups**
- **Paraphrase Group Leakage Check**: **0 overlapping paraphrase groups** across `train ∩ val`, `train ∩ test`, and `val ∩ test` (`paraphrase_split_zero_leakage: true`).

---

## 3. Architectural Boundary

Per the implementation specification, `LocalIntentClassifier` in [`Backend/services/ai/classifier.py`](file:///D:/Projects/PMS_Dashboard/Backend/services/ai/classifier.py) is restricted strictly to proposing `RouterIntentType` (`intent`, `confidence`, `abstain`):
- It **never** resolves entities (`team`, `branch`, `position`, `metric`, `periods`).
- It **never** checks or overrides RBAC permissions (`restricted_access` is enforced deterministically before any data read).
- It **never** calculates or formats KPI values.

---

## 4. Held-Out Comparison: Legacy Router vs. Hybrid Rules vs. Local Classifier

| Split | Questions | Legacy Keyword Router Exact Match | `HybridQueryRouter` (Local Rules) Exact Match | `HybridQueryRouter` Provider Calls | Classifier Accepted (`th=0.35`) | Classifier Precision on Accepted | Provider Call Reduction vs. Hybrid |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`train`** | 57 | 40.35% (23/57) | **100.0%** (57/57) | 0 | 20/57 (35.1%) | **100.0%** (20/20) | 0.0% |
| **`val`** | 22 | 54.55% (12/22) | **100.0%** (22/22) | 0 | 3/22 (13.6%) | **100.0%** (3/3) | 0.0% |
| **`test`** | 47 | 31.91% (15/47) | **100.0%** (47/47) | 0 | 14/47 (29.8%) | **100.0%** (14/14) | **0.0%** |

### Threshold Sensitivity on Held-Out `test` Split (47 Questions)

| Confidence Threshold | Accepted Count (`test`) | Abstained Count (`test`) | Accepted Exact Match Precision | Meets `>= 99%` Precision Gate? |
| :---: | :---: | :---: | :---: | :---: |
| `0.25` | 23 / 47 (48.9%) | 24 / 47 | 87.0% (20 / 23) | No |
| `0.35` (calibrated on `val`) | 14 / 47 (29.8%) | 33 / 47 | **100.0%** (14 / 14) | **Yes** |
| `0.45` | 8 / 47 (17.0%) | 39 / 47 | **100.0%** (8 / 8) | **Yes** |
| `0.55` | 4 / 47 (8.5%) | 43 / 47 | **100.0%** (4 / 4) | **Yes** |

---

## 5. Promotion Gate Verification Summary

| Gate Criterion | Target | Measured (`test`) | Status |
| :--- | :---: | :---: | :---: |
| Paraphrase-grouped split leakage | `0` shared groups | `0` shared groups | **PASS** |
| Overall held-out exact intent & filter match | `>= 95.0%` | **100.0%** (`47/47`) | **PASS** |
| Classifier exact match among accepted local requests | `>= 99.0%` | **100.0%** (`14/14` at `th=0.35`) | **PASS** |
| Provider call reduction vs. Rules + Gemini fallback | `>= 20.0%` | **0.0%** (`HybridQueryRouter` uses `0` calls) | **FAIL (Not Needed)** |
| **Final Promotion Decision** | Pass all gates | Keep `AI_CLASSIFIER_MODE=off` | **DO NOT PROMOTE** |
