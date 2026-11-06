from __future__ import annotations

import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.ai_schemas import AiChatRequest, ConfirmedQueryContext, SessionFilterContext
from models.schemas import CallsData, EvaluationData, GeoBreakdown, GeoData, PerformanceRecord
from services.ai.catalog import ai_evidence_cache, get_ai_catalog
from services.ai.orchestrator import PmsAiOrchestrator
from services.ai.router import HybridQueryRouter
from services.dashboard_record_service import DashboardRecordService


def _build_benchmark_records(employees_per_team: int = 200) -> list[PerformanceRecord]:
    teams_spec = [
        ("Inbound", "EGY", "Call Center Agent", "Other", "Abandon Rate"),
        ("Outbound", "EGY", "Call Center Agent", "Other", "Reachability"),
        ("Coding", "EGY", "Medical Coder", "Accuracy", "Coding Accuracy"),
        ("Marketing", "UAE", "Media Buyer", "CPL", "CPL"),
        ("Pharmacy", "UAE", "AJM Pharmacy Manager", "Leakage", "Leakage"),
    ]
    records: list[PerformanceRecord] = []
    for team_name, region, position, other_key, other_label in teams_spec:
        for idx in range(1, employees_per_team + 1):
            emp_id = f"{team_name[:3].upper()}{idx:04d}"
            score = round(68.0 + ((idx * 7) % 31), 1)
            shj_att = 25 + (idx % 20)
            shj_book = 45 + (idx % 25)
            dxb_att = 55 + (idx % 35)
            dxb_book = 90 + (idx % 40)
            tot_att = shj_att + dxb_att
            tot_book = shj_book + dxb_book
            att_rate = tot_att / tot_book
            records.append(
                PerformanceRecord(
                    id=f"{team_name}_{emp_id}_2026_09",
                    employee_id=emp_id,
                    employee_name=f"Agent {team_name} {idx:03d}",
                    team=team_name,
                    month="September",
                    year=2026,
                    region=region,
                    position=position,
                    performance_level="Employee",
                    status="Below Target" if score < 80 else "On Track",
                    evaluation=EvaluationData(score=score, grade="C" if score < 80 else "B"),
                    calls=CallsData(inbound=380, total_handled=490, abandoned=12),
                    geo=GeoData(
                        bookings=GeoBreakdown(dubai=dxb_book, sharjah=shj_book, ajman=20, clinics=12),
                        attended=GeoBreakdown(dubai=dxb_att, sharjah=shj_att, ajman=15, clinics=9),
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
                            "actual_value": 0.29,
                            "target_value": 0.30,
                            "weight_applied": 0.20,
                            "contribution": (0.29 / 0.30) * 0.20,
                        },
                        {
                            "kpi_key": other_key,
                            "label": other_label,
                            "actual_value": 0.055 if team_name == "Inbound" else 0.88,
                            "target_value": 0.05 if team_name == "Inbound" else 0.90,
                            "weight_applied": 0.10,
                            "contribution": 0.085,
                        },
                    ],
                )
            )
    return records


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return round(ordered[idx], 2)


def evaluate_held_out_routing() -> dict[str, Any]:
    fixture_path = BACKEND_DIR / "tests" / "fixtures" / "ai_english_questions.json"
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    questions = data["questions"]

    by_split: dict[str, list[bool]] = {}
    by_scope: dict[str, list[bool]] = {}
    by_intent: dict[str, list[bool]] = {}

    for q in questions:
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

        res = HybridQueryRouter(scope=q_scope).resolve_and_validate(prompt=q["prompt"], session_state=ss)
        exp_f = q.get("expected_filters") or {}
        ok = (
            res.outcome == q["expected_outcome"]
            and res.plan.intent == q["expected_intent"]
            and all(getattr(res.plan, k) == v for k, v in exp_f.items())
        )
        by_split.setdefault(q["split"], []).append(ok)
        by_scope.setdefault(q["scope_category"], []).append(ok)
        by_intent.setdefault(q["expected_intent"], []).append(ok)

    return {
        "total_questions": len(questions),
        "overall_exact_match_pct": round(100.0 * sum(sum(v) for v in by_split.values()) / len(questions), 2),
        "by_split": {
            k: {"matched": sum(v), "total": len(v), "pct": round(100.0 * sum(v) / len(v), 2)}
            for k, v in sorted(by_split.items())
        },
        "by_scope_category": {
            k: {"matched": sum(v), "total": len(v), "pct": round(100.0 * sum(v) / len(v), 2)}
            for k, v in sorted(by_scope.items())
        },
        "by_intent": {
            k: {"matched": sum(v), "total": len(v), "pct": round(100.0 * sum(v) / len(v), 2)}
            for k, v in sorted(by_intent.items())
        },
    }


def run_200_employee_benchmark() -> dict[str, Any]:
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "bench_ai.db"
        engine = create_engine(
            f"sqlite:///{db_path.as_posix()}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
            conn.exec_driver_sql("PRAGMA synchronous=NORMAL;")
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine)

        records = _build_benchmark_records(employees_per_team=200)
        orig_list_records = DashboardRecordService.list_records
        orig_list_analysis = DashboardRecordService.list_analysis_records
        orig_list_index = DashboardRecordService.list_record_index

        DashboardRecordService.list_records = lambda _self, **_kw: records  # type: ignore[method-assign]
        DashboardRecordService.list_analysis_records = lambda _self, **_kw: records  # type: ignore[method-assign]
        DashboardRecordService.list_record_index = lambda _self: None  # type: ignore[method-assign]

        try:
            gm_scope = {
                "role": "General Manager",
                "user_id": "00000000-0000-0000-0000-000000000002",
                "has_unrestricted_team_access": True,
            }

            workloads = {
                "routine_local": [
                    AiChatRequest(
                        prompt="What is the Attendance score in September 2026?",
                        session_state=SessionFilterContext(function="Call Center"),
                    ),
                    AiChatRequest(
                        prompt="What is the Inbound team score in September 2026?",
                        session_state=SessionFilterContext(function="Call Center", team="Inbound"),
                    ),
                    AiChatRequest(
                        prompt="What is the Outbound team score in September 2026?",
                        session_state=SessionFilterContext(function="Call Center", team="Outbound"),
                    ),
                    AiChatRequest(
                        prompt="Show overdue corrective actions in Call Center for September 2026",
                        session_state=SessionFilterContext(function="Call Center"),
                    ),
                ],
                "single_kpi": [
                    AiChatRequest(
                        prompt="What is Inbound Patient Attendance Rate vs target in September 2026?",
                        session_state=SessionFilterContext(function="Call Center", team="Inbound"),
                    ),
                    AiChatRequest(
                        prompt="What is Inbound Abandon Rate vs target in September 2026?",
                        session_state=SessionFilterContext(function="Call Center", team="Inbound"),
                    ),
                    AiChatRequest(
                        prompt="How is Outbound Reachability against target in September 2026?",
                        session_state=SessionFilterContext(function="Call Center", team="Outbound"),
                    ),
                    AiChatRequest(
                        prompt="What is Outbound AHT in September 2026?",
                        session_state=SessionFilterContext(function="Call Center", team="Outbound"),
                    ),
                ],
                "standard_comparison": [
                    AiChatRequest(
                        prompt="Compare Dubai and Sharjah Inbound Attendance Rate in September 2026",
                        session_state=SessionFilterContext(function="Call Center", team="Inbound"),
                    ),
                    AiChatRequest(
                        prompt="Compare all UAE branches Attendance and Booking conversion for Call Center in September 2026",
                        session_state=SessionFilterContext(function="Call Center"),
                    ),
                    AiChatRequest(
                        prompt="Which Call Center team dropped the most in September 2026?",
                        session_state=SessionFilterContext(function="Call Center"),
                    ),
                    AiChatRequest(
                        prompt="Diagnose Outbound KPI gaps in September 2026",
                        session_state=SessionFilterContext(function="Call Center", team="Outbound"),
                    ),
                ],
            }

            results: dict[str, Any] = {
                "employees_per_team": 200,
                "teams_seeded": 5,
                "total_records_in_memory": len(records),
                "categories": {},
            }

            for cat_name, req_list in workloads.items():
                # 1. Cold cache measurement
                ai_evidence_cache.clear()
                cold_latencies: list[float] = []
                for req in req_list:
                    with SessionLocal() as db:
                        t0 = time.perf_counter()
                        PmsAiOrchestrator(db, gm_scope).run_chat_turn(req.model_copy(deep=True))
                        cold_latencies.append((time.perf_counter() - t0) * 1000.0)

                # 2. Warm cache concurrent measurement (4 concurrent workers x 3 passes = 12 turns per category)
                def _run_one(r: AiChatRequest) -> float:
                    with SessionLocal() as db:
                        t0 = time.perf_counter()
                        PmsAiOrchestrator(db, gm_scope).run_chat_turn(r.model_copy(deep=True))
                        return (time.perf_counter() - t0) * 1000.0

                warm_reqs = req_list * 3
                with ThreadPoolExecutor(max_workers=4) as pool:
                    warm_latencies = list(pool.map(_run_one, warm_reqs))

                results["categories"][cat_name] = {
                    "cold_p50_ms": _percentile(cold_latencies, 50),
                    "cold_p95_ms": _percentile(cold_latencies, 95),
                    "cold_mean_ms": round(statistics.mean(cold_latencies), 2),
                    "warm_p50_ms": _percentile(warm_latencies, 50),
                    "warm_p95_ms": _percentile(warm_latencies, 95),
                    "warm_mean_ms": round(statistics.mean(warm_latencies), 2),
                }

            engine.dispose()
            return results
        finally:
            DashboardRecordService.list_records = orig_list_records  # type: ignore[method-assign]
            DashboardRecordService.list_analysis_records = orig_list_analysis  # type: ignore[method-assign]
            DashboardRecordService.list_record_index = orig_list_index  # type: ignore[method-assign]


if __name__ == "__main__":
    routing_eval = evaluate_held_out_routing()
    cert_registry = get_ai_catalog().get_scope_certification_registry()
    bench = run_200_employee_benchmark()
    summary = {
        "routing_evaluation": routing_eval,
        "certified_scopes_count": sum(1 for r in cert_registry if r["certified"]),
        "total_scopes_count": len(cert_registry),
        "benchmark_200_emp_per_team": bench,
    }
    print(json.dumps(summary, indent=2))
