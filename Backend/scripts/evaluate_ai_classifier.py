from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.ai_schemas import AiChatRequest, ConfirmedQueryContext, SessionFilterContext
from models.schemas import CallsData, EvaluationData, GeoBreakdown, GeoData, PerformanceRecord
from services.ai.catalog import ai_evidence_cache
from services.ai.classifier import LocalIntentClassifier
from services.ai.domain_policies import extract_prompt_signals
from services.ai.orchestrator import PmsAiOrchestrator
from services.ai.router import HybridQueryRouter
from services.dashboard_record_service import DashboardRecordService


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


def _build_v2_scenario_fixture_records() -> list[PerformanceRecord]:
    def _mk(
        emp_id: str,
        name: str,
        team: str,
        score: float,
        shj_att: int,
        shj_book: int,
        dxb_att: int,
        dxb_book: int,
        month: str = "September",
        position: str = "Call Center Agent",
        ajm_book: int = 20,
        ajm_att: int = 15,
    ) -> PerformanceRecord:
        tot_att = shj_att + dxb_att
        tot_book = shj_book + dxb_book
        att_rate = (tot_att / tot_book) if tot_book > 0 else 0.0
        return PerformanceRecord(
            id=f"{team}_{emp_id}_2026_{month[:3]}",
            employee_id=emp_id,
            employee_name=name,
            team=team,
            month=month,
            year=2026,
            region="EGY",
            position=position,
            performance_level="Employee",
            status="Below Target" if score < 80 else "On Track",
            evaluation=EvaluationData(score=score, grade="C" if score < 80 else "B"),
            calls=CallsData(inbound=400, total_handled=500, abandoned=15),
            geo=GeoData(
                bookings=GeoBreakdown(dubai=dxb_book, sharjah=shj_book, ajman=ajm_book, clinics=10),
                attended=GeoBreakdown(dubai=dxb_att, sharjah=shj_att, ajman=ajm_att, clinics=8),
            ),
            kpi_values=[
                {
                    "kpi_key": "Attendance",
                    "label": "Attendance Rate",
                    "actual_value": att_rate,
                    "target_value": 0.65,
                    "weight_applied": 0.70,
                    "contribution": min(att_rate / 0.65, 1.0) * 0.70,
                },
                {
                    "kpi_key": "Booking",
                    "label": "Booking Rate",
                    "actual_value": 0.28,
                    "target_value": 0.30,
                    "weight_applied": 0.10,
                    "contribution": (0.28 / 0.30) * 0.10,
                },
            ],
        )

    recs: list[PerformanceRecord] = []
    # Adham Tarek (EMP501): March-September 2026, worst in March (82.0%), best in August (96.5%)
    for m_name, sc in (
        ("March", 82.0),
        ("April", 85.0),
        ("May", 87.5),
        ("June", 90.0),
        ("July", 91.0),
        ("August", 96.5),
        ("September", 91.0),
    ):
        recs.append(_mk("EMP501", "Adham Tarek", "Inbound", sc, 45, 60, 120, 150, month=m_name, ajm_book=85, ajm_att=65))

    # 3 Mariam/Maryam records in Inbound (for phonetic/disambiguation + Mariam Ali earliest July 2026)
    for m_name in ("July", "August", "September"):
        recs.append(_mk("EMP601", "Mariam Ali", "Inbound", 88.0, 30, 50, 80, 100, month=m_name, ajm_book=20, ajm_att=15))
    for m_name in ("August", "September"):
        recs.append(_mk("SGHD70231", "Mariam Mohssen Mahmoud", "Inbound", 94.4, 25, 45, 70, 95, month=m_name, ajm_book=10, ajm_att=8))
    recs.append(_mk("SGHD70250", "Maryam Elsayed Mahmoud Eid", "Inbound", 83.9, 0, 0, 0, 0, month="September", ajm_book=10, ajm_att=8))

    # Support Positions (stored under team="Call Center" with position)
    recs.append(_mk("EMP701", "Kareem Adel", "Call Center", 62.0, 0, 0, 0, 0, month="September", position="Quality Assurance"))
    recs.append(_mk("EMP702", "Ziad Nabil", "Call Center", 62.0, 0, 0, 0, 0, month="September", position="Trainer"))
    recs.append(_mk("EMP703", "Nour Hassan", "Call Center", 93.0, 0, 0, 0, 0, month="September", position="Workforce analyst"))

    # Coding record for RCM Director scenario
    recs.append(_mk("COD301", "Heba Mostafa", "Coding", 92.1, 0, 0, 0, 0, month="September", position="Medical Coder"))
    return recs


def evaluate_v2_conversation_scenarios() -> dict[str, Any]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from config.database import Base

    scenario_path = BACKEND_DIR / "tests" / "fixtures" / "ai_questions" / "conversation_v2_scenarios.jsonl"
    if not scenario_path.exists():
        return {"total_scenarios": 0, "by_split": {}, "scenarios": []}

    lines = [
        json.loads(line)
        for line in scenario_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    records = _build_v2_scenario_fixture_records()

    orig_list_records = DashboardRecordService.list_records
    orig_list_analysis = DashboardRecordService.list_analysis_records
    orig_list_index = DashboardRecordService.list_record_index
    DashboardRecordService.list_records = lambda _self, **_kw: records  # type: ignore[method-assign]
    DashboardRecordService.list_analysis_records = lambda _self, **_kw: records  # type: ignore[method-assign]
    DashboardRecordService.list_record_index = lambda _self: None  # type: ignore[method-assign]

    try:
        ai_evidence_cache.clear()
        by_split: dict[str, list[bool]] = {"train": [], "val": [], "test": []}
        scenario_details: list[dict[str, Any]] = []

        with SessionLocal() as db:
            for item in lines:
                role = item.get("role") or "General Manager"
                scope: dict[str, Any] = {
                    "role": role,
                    "user_id": f"eval-{item['scenario_id']}",
                }
                if item.get("accessible_teams") is not None:
                    scope["has_unrestricted_team_access"] = False
                    scope["accessible_functions"] = item.get("accessible_functions") or ["Call Center"]
                    scope["accessible_teams"] = item["accessible_teams"]
                elif item.get("accessible_functions") is not None:
                    scope["has_unrestricted_team_access"] = False
                    scope["accessible_functions"] = item["accessible_functions"]
                else:
                    scope["has_unrestricted_team_access"] = True

                if item.get("accessible_branches") is not None:
                    scope["accessible_branches"] = item["accessible_branches"]
                    scope["allowed_branches"] = item["accessible_branches"]

                ss_dict = dict(item.get("session_state") or {"function": "Call Center"})
                if item.get("prior_confirmed_query"):
                    ss_dict["last_confirmed_query"] = ConfirmedQueryContext(**item["prior_confirmed_query"])
                ss = SessionFilterContext(**ss_dict)

                res = PmsAiOrchestrator(db, scope).run_chat_turn(
                    AiChatRequest(prompt=item["prompt"], session_state=ss)
                )

                outcome_ok = res.outcome == item["expected_outcome"]
                clar_ok = True
                if item.get("expected_clarification_code"):
                    actual_code = res.clarification.code if res.clarification else None
                    clar_ok = actual_code == item["expected_clarification_code"]

                op_ok = True
                if item.get("expected_operation_kind") and res.validated_plan_v2:
                    op_kinds = [op.kind for op in res.validated_plan_v2.operations]
                    op_ok = item["expected_operation_kind"] in op_kinds

                zero_reads_ok = True
                if item.get("zero_performance_reads"):
                    zero_reads_ok = len(res.tool_calls) == 0

                must_contain_ok = True
                full_text = f"{res.headline} {' '.join(res.narrative_bullets)}".casefold()
                for token in item.get("expected_must_contain") or []:
                    if str(token).casefold() not in full_text:
                        must_contain_ok = False
                        break

                passed = bool(outcome_ok and clar_ok and op_ok and zero_reads_ok and must_contain_ok)
                split_key = item.get("split", "test")
                by_split.setdefault(split_key, []).append(passed)
                scenario_details.append(
                    {
                        "scenario_id": item["scenario_id"],
                        "split": split_key,
                        "passed": passed,
                        "actual_outcome": res.outcome,
                        "headline": res.headline,
                    }
                )

        total_passed = sum(1 for s in scenario_details if s["passed"])
        return {
            "total_scenarios": len(scenario_details),
            "passed_scenarios": total_passed,
            "exact_match_pct": round(100.0 * total_passed / len(scenario_details), 2) if scenario_details else 0.0,
            "by_split": {
                k: {
                    "matched": sum(v),
                    "total": len(v),
                    "pct": round(100.0 * sum(v) / len(v), 2) if v else 0.0,
                }
                for k, v in by_split.items()
            },
            "scenarios": scenario_details,
        }
    finally:
        DashboardRecordService.list_records = orig_list_records  # type: ignore[method-assign]
        DashboardRecordService.list_analysis_records = orig_list_analysis  # type: ignore[method-assign]
        DashboardRecordService.list_record_index = orig_list_index  # type: ignore[method-assign]
        engine.dispose()


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
        "v2_conversation_scenarios": evaluate_v2_conversation_scenarios(),
    }


if __name__ == "__main__":
    print(json.dumps(run_classifier_evaluation(), indent=2))
