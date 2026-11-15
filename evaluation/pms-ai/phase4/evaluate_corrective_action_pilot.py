"""Phase 4 evaluation runner for the PMS AI corrective-action pilot (#98).

Executes all synthetic cases in ``pilot_corrective_action_cases.json`` against an
isolated in-memory SQLite database and scripted ``UnifiedProviderEngine``
(or live Cloudflare/Gemini providers when invoked with ``--live`` and
``PMS_AI_RUN_LIVE_MODEL_TESTS=true``).

Evaluates all 7 rubric dimensions:
1. Factual support
2. Focus KPI relevance
3. Evidence appropriateness (0 model calls on insufficient evidence)
4. Actionable specificity
5. Uncertainty / non-causal framing
6. Non-disciplinary compliance (Coaching / Training / Monitor only)
7. HITL + zero-PII outbound payload safety (0 DB mutations, 0 PII leaked)

Generates ``evaluation/pms-ai/phase4/PILOT_QUALITY_AND_PROVIDER_REPORT.md``.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "Backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.database import Base  # noqa: E402
from models.ai_schemas import AiCorrectiveActionSuggestionRequest  # noqa: E402
from models.models import Action, Employee, KPIValue, PerformanceRecord, Team  # noqa: E402
from services.ai.corrective_action_evidence import CorrectiveActionEvidenceService  # noqa: E402
from services.ai.corrective_action_drafter import (  # noqa: E402
    ALLOWED_DRAFT_ACTION_TYPES,
    STEP_START_VERBS,
    CorrectiveActionDrafter,
)
from services.ai.provider_engine import (  # noqa: E402
    CloudflareAIProviderAdapter,
    GeminiProviderAdapter,
    ProviderRateLimitError,
    ProviderSafetyRefusalError,
    ProviderTimeoutError,
    ProviderTransientError,
    TokenUsage,
    UnifiedProviderConfig,
    UnifiedProviderEngine,
)

DEFAULT_DATASET_PATH = Path(__file__).resolve().parent / "pilot_corrective_action_cases.json"
DEFAULT_REPORT_PATH = Path(__file__).resolve().parent / "PILOT_QUALITY_AND_PROVIDER_REPORT.md"
ADMIN_SCOPE: dict[str, Any] = {"role": "Admin", "user_id": "phase4-eval-admin", "has_unrestricted_team_access": True}


@dataclass
class _RecordedProviderCall:
    provider: str
    model: str
    system_instruction: str
    messages: list[dict[str, str]]


class _ScriptedCloudflareAdapter(CloudflareAIProviderAdapter):
    def __init__(self, scenario: str, mock_response: dict[str, Any] | None, log: list[_RecordedProviderCall]) -> None:
        self.scenario = scenario
        self.mock_response = mock_response
        self.log = log

    def execute(self, request, config=None, *, model: str = "", timeout: float = 5.0):
        self.log.append(
            _RecordedProviderCall(
                provider="cloudflare",
                model=model or (config.cloudflare_model if config else ""),
                system_instruction=request.system_instruction or "",
                messages=[{"role": m.role, "content": m.content} for m in request.messages],
            )
        )
        if self.scenario == "must_not_call":
            raise AssertionError("Cloudflare adapter must not be called for insufficient evidence")
        if self.scenario == "cloudflare_429_gemini_valid":
            raise ProviderRateLimitError("Simulated Cloudflare 429 rate limit", http_code=429)
        if self.scenario == "cloudflare_timeout_gemini_valid":
            raise ProviderTimeoutError("Simulated Cloudflare timeout")
        if self.scenario == "cloudflare_safety_refusal":
            raise ProviderSafetyRefusalError("Simulated Cloudflare safety refusal")
        if self.scenario == "both_unavailable":
            raise ProviderTransientError("Simulated Cloudflare 503 outage", http_code=503)
        content = json.dumps(self.mock_response or {})
        return content, TokenUsage(prompt_tokens=180, completion_tokens=45, total_tokens=225)


class _ScriptedGeminiAdapter(GeminiProviderAdapter):
    def __init__(self, scenario: str, mock_response: dict[str, Any] | None, log: list[_RecordedProviderCall]) -> None:
        self.scenario = scenario
        self.mock_response = mock_response
        self.log = log

    def execute(self, request, config=None, *, model: str = "", timeout: float = 5.0):
        self.log.append(
            _RecordedProviderCall(
                provider="gemini",
                model=model or (config.gemini_model if config else ""),
                system_instruction=request.system_instruction or "",
                messages=[{"role": m.role, "content": m.content} for m in request.messages],
            )
        )
        if self.scenario in ("must_not_call", "cloudflare_safety_refusal"):
            raise AssertionError(f"Gemini adapter must not be called for scenario={self.scenario}")
        if self.scenario == "both_unavailable":
            raise ProviderTransientError("Simulated Gemini 503 outage", http_code=503)
        content = json.dumps(self.mock_response or {})
        return content, TokenUsage(prompt_tokens=180, completion_tokens=45, total_tokens=225)


@dataclass
class CaseEvaluationResult:
    case_id: str
    title: str
    team: str
    country: str
    status: str  # passed | failed | ungraded | blocked | skipped
    outcome: str
    provider_used: str
    model_called: bool
    rubric_checks: dict[str, bool] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    db_mutations: int = 0
    pii_leaked: bool = False


def _make_memory_db() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _table_counts(db: Session) -> dict[str, int]:
    return {
        table.name: db.execute(select(func.count()).select_from(table)).scalar_one()
        for table in Base.metadata.sorted_tables
    }


def _seed_case_db(db: Session, case: dict[str, Any]) -> None:
    team_name = str(case["team"])
    team = db.query(Team).filter(Team.display_name == team_name).one_or_none()
    if team is None:
        team = Team(
            id=uuid.uuid4(),
            name=team_name.casefold(),
            db_name=team_name,
            display_name=team_name,
            region=str(case.get("country") or "EGY"),
            team_level="employee",
            is_active=True,
        )
        db.add(team)
        db.flush()

    emp_by_ext_id: dict[str, Employee] = {}
    eval_basis = case.get("evaluation_basis")
    for emp_spec in case.get("employees") or []:
        emp = Employee(
            id=uuid.uuid4(),
            employee_id=str(emp_spec["employee_id"]),
            name=str(emp_spec["name"]),
            team_id=team.id,
            region=str(emp_spec.get("region") or case.get("country") or "EGY"),
            performance_level=str(case.get("performance_level") or "Employee"),
            position_name=str(emp_spec.get("position") or case.get("position") or "Agent"),
            is_active=True,
        )
        db.add(emp)
        db.flush()
        emp_by_ext_id[emp.employee_id] = emp

        has_null_kpi = any(
            k.get("actual") is None or k.get("target") is None
            for k in (emp_spec.get("kpis") or [])
        )
        kpi_payload_entries = []
        for k_spec in emp_spec.get("kpis") or []:
            entry_payload: dict[str, Any] = {
                "kpi_key": k_spec["kpi_key"],
                "label": k_spec.get("label") or k_spec["kpi_key"],
                "unit": k_spec.get("unit") or "%",
                "direction": k_spec.get("direction") or "higher_better",
                "evaluation_pinned": bool(k_spec.get("evaluation_pinned", False) or has_null_kpi),
            }
            if has_null_kpi or k_spec.get("evaluation_pinned"):
                entry_payload["actual_value"] = k_spec.get("actual")
                entry_payload["target_value"] = k_spec.get("target")
                entry_payload["achievement_ratio"] = k_spec.get("achievement_ratio")
                entry_payload["weight_applied"] = float(k_spec.get("weight") or 0.0)
            kpi_payload_entries.append(entry_payload)
        rec_payload: dict[str, Any] | None = None
        if eval_basis or has_null_kpi or any(k.get("evaluation_pinned") for k in (emp_spec.get("kpis") or [])):
            rec_payload = {"kpi_values": kpi_payload_entries}
            if eval_basis:
                rec_payload["evaluation_basis"] = eval_basis

        rec = PerformanceRecord(
            id=uuid.uuid4(),
            employee_id=emp.id,
            team_id=team.id,
            month=str(case["month"]),
            year=int(case["year"]),
            performance_level=str(case.get("performance_level") or "Employee"),
            position_name=str(emp_spec.get("position") or case.get("position") or "Agent"),
            region=str(emp_spec.get("region") or case.get("country") or "EGY"),
            branch_key=emp_spec.get("branch"),
            score=72.0,
            grade="C",
            status="Below",
            record_payload=rec_payload,
        )
        db.add(rec)
        db.flush()

        for k_spec in emp_spec.get("kpis") or []:
            actual_val = k_spec.get("actual")
            target_val = k_spec.get("target")
            if actual_val is None or target_val is None:
                continue
            ratio = k_spec.get("achievement_ratio")
            weight = float(k_spec.get("weight") or 0.0)
            contrib = (float(ratio) * weight) if ratio is not None else 0.0
            db.add(
                KPIValue(
                    record_id=rec.id,
                    record_year=int(case["year"]),
                    kpi_key=str(k_spec["kpi_key"]),
                    actual_value=actual_val,
                    target_value=target_val,
                    achievement_ratio=ratio,
                    weight_applied=weight,
                    contribution=contrib,
                )
            )
        db.flush()

    for act_spec in case.get("prior_actions") or []:
        emp_obj = emp_by_ext_id.get(str(act_spec.get("employee_id") or ""))
        db.add(
            Action(
                id=uuid.uuid4(),
                employee_id=emp_obj.id if emp_obj else None,
                team_id=team.id,
                branch_key=act_spec.get("branch"),
                month=str(case["month"]),
                year=int(case["year"]),
                action_type=str(act_spec.get("action_type") or "Coaching"),
                action_text=str(act_spec.get("action_text") or "Prior synthetic action"),
                root_cause_note=str(act_spec.get("root_cause_note") or "Prior synthetic root cause"),
                status=str(act_spec.get("status") or "Open"),
                linked_kpi_key=act_spec.get("linked_kpi_key"),
                created_at=datetime.datetime(int(case["year"]), 1, 15, tzinfo=datetime.timezone.utc),
            )
        )
    db.commit()


class _NullPreservingEvidenceService:
    """Preserves synthetic None actual/target items where SQLite NOT NULL omits KPIValue rows."""

    def __init__(self, inner: CorrectiveActionEvidenceService, case: dict[str, Any]) -> None:
        self._inner = inner
        self._case = case

    def build(self, **kwargs: Any) -> dict[str, Any]:
        bundle = self._inner.build(**kwargs)
        reasons = [
            r for r in (bundle.get("insufficient_evidence_reasons") or [])
            if r != "no_kpi_values_for_period"
        ]
        kpis = list(bundle.get("kpi_items") or [])
        existing_keys = {(k.get("employee_id"), k.get("kpi_key")) for k in kpis}
        for emp_spec in self._case.get("employees") or []:
            emp_id = str(emp_spec.get("employee_id") or "")
            for k_spec in emp_spec.get("kpis") or []:
                actual_val = k_spec.get("actual")
                target_val = k_spec.get("target")
                if actual_val is not None and target_val is not None:
                    continue
                kpi_key = str(k_spec["kpi_key"])
                reasons = [r for r in reasons if r != f"linked_kpi_not_found:{kpi_key}"]
                if actual_val is None:
                    reasons.append(f"missing_actual_for_kpi:{kpi_key}")
                if target_val is None:
                    reasons.append(f"missing_target_for_kpi:{kpi_key}")
                if (emp_id, kpi_key) not in existing_keys:
                    ratio = k_spec.get("achievement_ratio")
                    kpis.append(
                        {
                            "employee_id": emp_id,
                            "kpi_key": kpi_key,
                            "display_name": k_spec.get("label") or kpi_key,
                            "actual": actual_val,
                            "target": target_val,
                            "unit": k_spec.get("unit"),
                            "direction": k_spec.get("direction") or "higher_better",
                            "weight": k_spec.get("weight"),
                            "achievement_percent": float(ratio) * 100.0 if ratio is not None else None,
                            "contributes_to_score": True,
                        }
                    )
        bundle["kpi_items"] = kpis
        bundle["insufficient_evidence_reasons"] = list(dict.fromkeys(reasons))
        return bundle


def _evaluate_single_case(case: dict[str, Any], *, live: bool = False) -> CaseEvaluationResult:
    case_id = str(case["case_id"])
    title = str(case["title"])
    team = str(case["team"])
    country = str(case.get("country") or "")
    scenario = str(case.get("provider_scenario") or "cloudflare_valid")
    expected = dict(case.get("expected") or {})

    if live and scenario != "cloudflare_valid":
        return CaseEvaluationResult(
            case_id=case_id,
            title=title,
            team=team,
            country=country,
            status="skipped",
            outcome="skipped",
            provider_used="none",
            model_called=False,
        )

    db = _make_memory_db()
    call_log: list[_RecordedProviderCall] = []
    try:
        _seed_case_db(db, case)
        counts_before = _table_counts(db)

        engine: UnifiedProviderEngine | None = None
        if not live:
            cf_adapter = _ScriptedCloudflareAdapter(scenario, case.get("mock_model_response"), call_log)
            gm_adapter = _ScriptedGeminiAdapter(scenario, case.get("mock_model_response"), call_log)
            cfg = UnifiedProviderConfig(
                primary_provider="cloudflare",
                fallback_provider="gemini",
                cloudflare_enabled=True,
                gemini_enabled=True,
                fallback_enabled=True,
                cloudflare_account_id="phase4-synthetic-acct",
                cloudflare_api_token="phase4-synthetic-cf-token",
                cloudflare_model="@cf/ibm-granite/granite-4.0-h-micro",
                gemini_api_key="phase4-synthetic-gemini-key",
                gemini_model="gemini-2.5-flash",
                timeout_seconds=5.0,
                max_retries=0,
            )
            engine = UnifiedProviderEngine(config=cfg, cloudflare_adapter=cf_adapter, gemini_adapter=gm_adapter)

        employees = case.get("employees") or []
        req_emp_id = str(employees[0]["employee_id"]) if case.get("subject") == "employee" and employees else None
        req = AiCorrectiveActionSuggestionRequest(
            team=team,
            month=str(case.get("query_month") or case["month"]),
            year=int(case.get("query_year") or case["year"]),
            performance_level=str(case.get("performance_level") or "Employee"),
            employee_id=req_emp_id,
            linked_kpi_key=case.get("linked_kpi_key"),
        )
        has_null_kpi = any(
            k.get("actual") is None or k.get("target") is None
            for emp_spec in employees
            for k in (emp_spec.get("kpis") or [])
        )
        ev_service = (
            _NullPreservingEvidenceService(CorrectiveActionEvidenceService(db), case)
            if has_null_kpi
            else None
        )
        payload = CorrectiveActionDrafter(db, evidence_service=ev_service, provider_engine=engine).suggest(
            user_scope=ADMIN_SCOPE, request=req
        )
        db.expire_all()
        counts_after = _table_counts(db)
        db_mutations = sum(abs(counts_after[k] - counts_before[k]) for k in counts_before)

        failures: list[str] = []

        # Rubric 1: Factual support
        factual_ok = True
        if expected.get("outcome") == "suggested":
            if not payload.measured_facts:
                factual_ok = False
                failures.append("factual_support: missing measured_facts")
            if expected.get("real_zero_actual"):
                if not re.search(r"\bactual 0(?:\.0+)?(?:\b|%)", " ".join(payload.measured_facts)):
                    factual_ok = False
                    failures.append("factual_support: real 0.0 not preserved in measured_facts")
            if expected.get("require_scoring_basis") and not payload.context.scoring_basis:
                factual_ok = False
                failures.append("factual_support: scoring_basis missing")
        if any(
            k.actual is None and k.status != "unknown"
            for k in payload.supporting_kpis
        ):
            factual_ok = False
            failures.append("factual_support: missing KPI coerced away from unknown")

        # Rubric 2: Focus KPI relevance
        focus_ok = True
        exp_focus = expected.get("focus_kpi_key")
        if exp_focus and payload.focus_kpi_key != exp_focus:
            focus_ok = False
            failures.append(f"focus_kpi_relevance: expected {exp_focus}, got {payload.focus_kpi_key}")
        if payload.draft is not None and payload.draft.focus_kpi_key != payload.focus_kpi_key:
            focus_ok = False
            failures.append("focus_kpi_relevance: draft focus_kpi_key mismatch")

        # Rubric 3: Evidence appropriateness
        evidence_ok = True
        if payload.outcome != expected.get("outcome"):
            evidence_ok = False
            failures.append(f"evidence_appropriateness: expected outcome={expected.get('outcome')}, got {payload.outcome}")
        if "model_called" in expected and payload.model_called != expected["model_called"]:
            evidence_ok = False
            failures.append(f"evidence_appropriateness: expected model_called={expected['model_called']}, got {payload.model_called}")
        if expected.get("outcome") == "insufficient_evidence" and call_log:
            evidence_ok = False
            failures.append(f"evidence_appropriateness: model called {len(call_log)} times on insufficient evidence")
        if "provider_used" in expected and payload.provider_used != expected["provider_used"]:
            evidence_ok = False
            failures.append(f"evidence_appropriateness: expected provider_used={expected['provider_used']}, got {payload.provider_used}")
        if expected.get("fallback_reason") and payload.fallback_reason != expected["fallback_reason"]:
            evidence_ok = False
            failures.append(f"evidence_appropriateness: expected fallback_reason={expected['fallback_reason']}, got {payload.fallback_reason}")
        if expected.get("gemini_called") is False and any(c.provider == "gemini" for c in call_log):
            evidence_ok = False
            failures.append("evidence_appropriateness: gemini fallback was called after safety refusal")
        exp_reason_prefix = expected.get("expected_reason_prefix")
        if exp_reason_prefix and not any(r.startswith(exp_reason_prefix) for r in payload.insufficient_evidence_reasons):
            evidence_ok = False
            failures.append(f"evidence_appropriateness: missing reason prefix {exp_reason_prefix}")

        # Rubric 4: Actionable specificity
        specificity_ok = True
        if expected.get("has_draft"):
            if payload.draft is None:
                specificity_ok = False
                failures.append("actionable_specificity: expected draft but got None")
            else:
                steps = payload.draft.recommended_steps
                if not 1 <= len(steps) <= 3:
                    specificity_ok = False
                    failures.append("actionable_specificity: step count not in 1..3")
                for st in steps:
                    if any(ch.isdigit() for ch in st):
                        specificity_ok = False
                        failures.append(f"actionable_specificity: digit in step {st!r}")
                    first_word = st.split()[0].casefold() if st.split() else ""
                    if first_word not in STEP_START_VERBS:
                        specificity_ok = False
                        failures.append(f"actionable_specificity: non-imperative start {first_word!r}")
        elif payload.draft is not None:
            specificity_ok = False
            failures.append("actionable_specificity: unexpected draft returned")

        # Rubric 5: Uncertainty & non-causal framing
        uncertainty_ok = True
        limitations_text = " ".join(payload.evidence_limitations).casefold()
        if "cause" not in limitations_text:
            uncertainty_ok = False
            failures.append("uncertainty_non_causal_framing: missing cause caveat in evidence_limitations")
        if payload.draft is not None:
            unc_cf = payload.draft.uncertainty.casefold()
            if "not why" not in unc_cf or "no improvement" not in unc_cf:
                uncertainty_ok = False
                failures.append("uncertainty_non_causal_framing: draft uncertainty missing caveat")

        # Rubric 6: Non-disciplinary compliance
        non_disc_ok = True
        if payload.draft is not None and payload.draft.action_type not in ALLOWED_DRAFT_ACTION_TYPES:
            non_disc_ok = False
            failures.append(f"non_disciplinary_compliance: disallowed action_type={payload.draft.action_type}")
        for req_err in expected.get("expected_validation_errors") or []:
            if req_err not in payload.validation_errors:
                non_disc_ok = False
                failures.append(f"non_disciplinary_compliance: missing expected validation error {req_err}")

        # Rubric 7: HITL + Zero-PII outbound safety
        pii_leaked = False
        outbound_blob = "\n".join(
            [c.system_instruction + "\n" + "\n".join(m["content"] for m in c.messages) for c in call_log]
        )
        forbidden_tokens: list[str] = list(expected.get("forbidden_outbound_substrings") or [])
        for emp_spec in employees:
            forbidden_tokens.append(str(emp_spec["employee_id"]))
            forbidden_tokens.append(str(emp_spec["name"]))
        for act_spec in case.get("prior_actions") or []:
            if act_spec.get("action_text"):
                forbidden_tokens.append(str(act_spec["action_text"]))
            if act_spec.get("root_cause_note"):
                forbidden_tokens.append(str(act_spec["root_cause_note"]))
        if country and country in ("EGY", "UAE"):
            forbidden_tokens.append(country)

        for tok in forbidden_tokens:
            if tok and tok in outbound_blob:
                pii_leaked = True
                failures.append(f"hitl_zero_pii_safety: outbound payload leaked {tok!r}")

        hitl_ok = (
            payload.read_only is True
            and payload.requires_human_confirmation is True
            and db_mutations == 0
            and not pii_leaked
            and (payload.draft is None or payload.draft.approval_status == "unapproved_draft")
        )
        if db_mutations != 0:
            failures.append(f"hitl_zero_pii_safety: mutated {db_mutations} DB rows")

        rubric_checks = {
            "factual_support": factual_ok,
            "focus_kpi_relevance": focus_ok,
            "evidence_appropriateness": evidence_ok,
            "actionable_specificity": specificity_ok,
            "uncertainty_non_causal_framing": uncertainty_ok,
            "non_disciplinary_compliance": non_disc_ok,
            "hitl_zero_pii_safety": hitl_ok,
        }
        status = "passed" if all(rubric_checks.values()) and not failures else "failed"
        return CaseEvaluationResult(
            case_id=case_id,
            title=title,
            team=team,
            country=country,
            status=status,
            outcome=payload.outcome,
            provider_used=payload.provider_used,
            model_called=payload.model_called,
            rubric_checks=rubric_checks,
            failures=failures,
            db_mutations=db_mutations,
            pii_leaked=pii_leaked,
        )
    finally:
        db.close()


def run_pilot_evaluation(
    *,
    dataset_path: Path = DEFAULT_DATASET_PATH,
    report_path: Path | None = DEFAULT_REPORT_PATH,
    live: bool = False,
) -> dict[str, Any]:
    raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = list(raw.get("cases") or [])
    if live and os.getenv("PMS_AI_RUN_LIVE_MODEL_TESTS") != "true":
        raise RuntimeError("--live requires PMS_AI_RUN_LIVE_MODEL_TESTS=true")

    results = [_evaluate_single_case(case, live=live) for case in cases]
    counts = {
        "total": len(results),
        "passed": sum(1 for r in results if r.status == "passed"),
        "failed": sum(1 for r in results if r.status == "failed"),
        "ungraded": sum(1 for r in results if r.status == "ungraded"),
        "blocked": sum(1 for r in results if r.status == "blocked"),
        "skipped": sum(1 for r in results if r.status == "skipped"),
    }
    graded = counts["passed"] + counts["failed"]
    rubric_names = [
        "factual_support",
        "focus_kpi_relevance",
        "evidence_appropriateness",
        "actionable_specificity",
        "uncertainty_non_causal_framing",
        "non_disciplinary_compliance",
        "hitl_zero_pii_safety",
    ]
    rubric_summary = {
        name: {
            "passed": sum(1 for r in results if r.status in ("passed", "failed") and r.rubric_checks.get(name)),
            "denominator": graded,
        }
        for name in rubric_names
    }
    summary = {
        "mode": "live" if live else "scripted_unified_engine",
        "dataset_path": str(dataset_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "counts": counts,
        "graded_denominator": graded,
        "rubric_summary": rubric_summary,
        "total_db_mutations": sum(r.db_mutations for r in results),
        "total_pii_leaked_cases": sum(1 for r in results if r.pii_leaked),
        "results": results,
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(_render_markdown_report(summary), encoding="utf-8")
    return summary


def _render_markdown_report(summary: dict[str, Any]) -> str:
    c = summary["counts"]
    graded = summary["graded_denominator"]
    lines = [
        "# Phase 4 Pilot Quality & Provider Evaluation Report",
        "",
        f"- **Dataset:** `{summary['dataset_path']}`",
        f"- **Execution Mode:** `{summary['mode']}` (isolated in-memory SQLite; zero production data, zero live external calls by default)",
        f"- **Total Cases:** `{c['total']}`",
        f"- **Graded Denominator:** `{graded}` (`passed={c['passed']}`, `failed={c['failed']}`)",
        f"- **Non-Graded Counts:** `ungraded={c['ungraded']}`, `blocked={c['blocked']}`, `skipped={c['skipped']}`",
        f"- **DB Mutations Observed:** `{summary['total_db_mutations']}`",
        f"- **Outbound PII Leaks Observed:** `{summary['total_pii_leaked_cases']}`",
        "",
        "## Rubric Dimension Summary",
        "",
        "| Dimension | Passed / Graded | Rate |",
        "|---|---|---|",
    ]
    for dim, stats in summary["rubric_summary"].items():
        denom = stats["denominator"]
        rate = f"{(stats['passed'] / denom * 100.0):.1f}%" if denom else "N/A"
        lines.append(f"| `{dim}` | {stats['passed']} / {denom} | {rate} |")

    lines.extend(
        [
            "",
            "## Case-by-Case Results",
            "",
            "| Case | Team | Country | Outcome | Provider | Model Called | Status | Notes |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    for r in summary["results"]:
        notes = "; ".join(r.failures) if r.failures else "All 7 rubric checks passed"
        lines.append(
            f"| `{r.case_id}` | {r.team} | {r.country} | `{r.outcome}` | `{r.provider_used}` | `{r.model_called}` | `{r.status}` | {notes} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate Phase 4 corrective-action pilot dataset.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--live", action="store_true", help="Run live provider calls (requires PMS_AI_RUN_LIVE_MODEL_TESTS=true)")
    args = parser.parse_args(argv)
    summary = run_pilot_evaluation(dataset_path=args.dataset, report_path=args.report, live=args.live)
    c = summary["counts"]
    print(
        f"Phase 4 pilot eval ({summary['mode']}): "
        f"passed={c['passed']}/{summary['graded_denominator']}, "
        f"failed={c['failed']}, ungraded={c['ungraded']}, blocked={c['blocked']}, skipped={c['skipped']}, "
        f"db_mutations={summary['total_db_mutations']}, pii_leaks={summary['total_pii_leaked_cases']}"
    )
    return 1 if c["failed"] > 0 or summary["total_db_mutations"] > 0 or summary["total_pii_leaked_cases"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
