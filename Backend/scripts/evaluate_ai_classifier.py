from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.ai_schemas import ConfirmedQueryContext, SessionFilterContext
from services.ai.classifier import LocalIntentClassifier
from services.ai.domain_policies import extract_prompt_signals
from services.ai.router import HybridQueryRouter


def _legacy_intent_from_signals(prompt: str, session_state: SessionFilterContext) -> str:
    sig = extract_prompt_signals(prompt, session_state)
    primary = sig.primary_intents[0] if sig.primary_intents else "executive_overview"
    if sig.asks_branch_comparison:
        return "compare_branches"
    if primary == "management_bsc":
        return "scorecard_structure"
    if primary == "corrective_actions":
        return "corrective_actions"
    if primary in ("people_contribution", "agent_spotlight_trend"):
        return "ranking"
    if primary == "team_trend_spotlight":
        return "trend"
    if primary == "kpi_diagnosis":
        return "actual_vs_target" if sig.detected_kpi else "score_drivers"
    return "current_value"


def run_classifier_evaluation() -> dict[str, Any]:
    fixture_path = BACKEND_DIR / "tests" / "fixtures" / "ai_english_questions.json"
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    questions = data["questions"]

    # 1. Verify paraphrase-grouped split integrity (zero leakage across train/val/test)
    groups_by_split: dict[str, set[str]] = {"train": set(), "val": set(), "test": set()}
    for q in questions:
        groups_by_split[q["split"]].add(q["paraphrase_group"])

    overlap_train_val = groups_by_split["train"] & groups_by_split["val"]
    overlap_train_test = groups_by_split["train"] & groups_by_split["test"]
    overlap_val_test = groups_by_split["val"] & groups_by_split["test"]
    zero_leakage = not (overlap_train_val or overlap_train_test or overlap_val_test)

    # 2. Train LocalIntentClassifier strictly on train split (threshold 0.35 calibrated on val)
    clf = LocalIntentClassifier.from_fixture_train_split(fixture_path, confidence_threshold=0.35)

    split_reports: dict[str, Any] = {}
    for split_name in ("train", "val", "test"):
        split_qs = [q for q in questions if q["split"] == split_name]
        legacy_matches = 0
        hybrid_matches = 0
        hybrid_provider_calls = 0

        clf_accepted = 0
        clf_accepted_exact = 0
        clf_abstained = 0
        clf_overall_exact_with_fallback = 0

        for q in split_qs:
            q_scope = dict(q.get("caller_scope") or {"role": q.get("caller_role", "General Manager")})
            if q.get("caller_branches") is not None:
                q_scope["accessible_branches"] = q["caller_branches"]
                q_scope["allowed_branches"] = q["caller_branches"]
            if q.get("caller_functions") is not None:
                q_scope["accessible_functions"] = q["caller_functions"]
            if not q.get("caller_branches") and not q.get("caller_functions"):
                q_scope.setdefault("has_unrestricted_team_access", True)

            ss_dict = dict(q.get("session_state") or {})
            if q.get("prior_confirmed_query"):
                ss_dict["last_confirmed_query"] = ConfirmedQueryContext(**q["prior_confirmed_query"])
            ss = SessionFilterContext(**ss_dict)

            # A. Legacy router evaluation
            leg_intent = _legacy_intent_from_signals(q["prompt"], ss)
            leg_sig = extract_prompt_signals(q["prompt"], ss)
            exp_f = q.get("expected_filters") or {}
            leg_team_ok = ("team" not in exp_f) or (leg_sig.detected_team == exp_f["team"])
            if leg_intent == q["expected_intent"] and q["expected_outcome"] == "answer" and leg_team_ok:
                legacy_matches += 1

            # B. HybridQueryRouter (Local Rules + Gemini Fallback)
            hyb_res = HybridQueryRouter(scope=q_scope).resolve_and_validate(prompt=q["prompt"], session_state=ss)
            hyb_ok = (
                hyb_res.outcome == q["expected_outcome"]
                and hyb_res.plan.intent == q["expected_intent"]
                and all(getattr(hyb_res.plan, k) == v for k, v in exp_f.items())
            )
            if hyb_ok:
                hybrid_matches += 1
            hybrid_provider_calls += hyb_res.provider_metrics.provider_calls

            # C. LocalIntentClassifier proposal + PMS entity/RBAC resolution
            pred = clf.predict(q["prompt"])
            # PMS still enforces pre-read validation (restricted_access, unavailable_data, unsupported_request, clarification)
            filters_ok = all(getattr(hyb_res.plan, k) == v for k, v in exp_f.items())
            outcome_ok = hyb_res.outcome == q["expected_outcome"]

            if not pred.abstain:
                clf_accepted += 1
                if pred.intent == q["expected_intent"] and outcome_ok and filters_ok:
                    clf_accepted_exact += 1
                    clf_overall_exact_with_fallback += 1
            else:
                clf_abstained += 1
                # When classifier abstains, it falls back to HybridQueryRouter / provider
                if hyb_ok:
                    clf_overall_exact_with_fallback += 1

        total = len(split_qs)
        accepted_precision_pct = (
            round(100.0 * clf_accepted_exact / clf_accepted, 2) if clf_accepted > 0 else 0.0
        )
        provider_call_reduction_pct = (
            round(100.0 * (hybrid_provider_calls - clf_abstained) / hybrid_provider_calls, 2)
            if hybrid_provider_calls > 0
            else 0.0
        )

        split_reports[split_name] = {
            "total_questions": total,
            "legacy_router_exact_match_pct": round(100.0 * legacy_matches / total, 2),
            "hybrid_router_exact_match_pct": round(100.0 * hybrid_matches / total, 2),
            "hybrid_router_provider_calls": hybrid_provider_calls,
            "classifier_backend": clf.backend_used,
            "classifier_confidence_threshold": clf.confidence_threshold,
            "classifier_accepted_count": clf_accepted,
            "classifier_abstained_count": clf_abstained,
            "classifier_accepted_exact_match_pct": accepted_precision_pct,
            "classifier_overall_exact_match_pct": round(
                100.0 * clf_overall_exact_with_fallback / total, 2
            ),
            "provider_call_reduction_vs_hybrid_pct": provider_call_reduction_pct,
        }

    test_rep = split_reports["test"]
    passes_precision_gate = test_rep["classifier_accepted_exact_match_pct"] >= 99.0
    passes_cost_gate = test_rep["provider_call_reduction_vs_hybrid_pct"] >= 20.0
    passes_overall_gate = test_rep["classifier_overall_exact_match_pct"] >= 95.0
    promote_classifier = bool(passes_precision_gate and passes_cost_gate and passes_overall_gate)

    return {
        "paraphrase_split_zero_leakage": zero_leakage,
        "paraphrase_groups_per_split": {k: len(v) for k, v in groups_by_split.items()},
        "splits": split_reports,
        "gates": {
            "accepted_local_exact_match_target_pct": 99.0,
            "accepted_local_exact_match_measured_pct": test_rep["classifier_accepted_exact_match_pct"],
            "passes_precision_gate": passes_precision_gate,
            "provider_call_reduction_target_pct": 20.0,
            "provider_call_reduction_measured_pct": test_rep["provider_call_reduction_vs_hybrid_pct"],
            "passes_cost_gate": passes_cost_gate,
            "overall_test_exact_match_target_pct": 95.0,
            "overall_test_exact_match_measured_pct": test_rep["classifier_overall_exact_match_pct"],
            "passes_overall_gate": passes_overall_gate,
        },
        "promotion_decision": "PROMOTE" if promote_classifier else "DO_NOT_PROMOTE_KEEP_HYBRID_RULES",
        "runtime_dependency_added": promote_classifier,
    }


if __name__ == "__main__":
    print(json.dumps(run_classifier_evaluation(), indent=2))
