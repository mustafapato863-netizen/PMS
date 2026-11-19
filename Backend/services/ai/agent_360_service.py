"""Agent 360° Profile Service.

Zero-LLM deterministic data assembly for an agent's self-service scorecard.
Reuses canonical KPIValue rows, scoring rules, What-If math, and corrective-action
history — does NOT duplicate scoring formulas.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from models.models import Employee, KPIValue, PerformanceRecord, Team
from services.ai.what_if_service import KpiInput, simulate_kpi_improvement
from services.corrective_action_service import CorrectiveActionService
from utils.scoring_rules import letter_grade

MONTH_ORDER: dict[str, int] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

_LOWER_BETTER_TOKENS = (
    "reject",
    "abandon",
    "aht",
    "wait",
    "hold",
    "missed",
    "error",
    "delay",
    "cancel",
    "no_show",
    "noshow",
    "complaint",
    "drop",
    "late",
    "absent",
)

MIN_COHORT_SIZE = 5


def _month_sort_key(record: PerformanceRecord) -> tuple[int, int]:
    year = int(record.year or 0)
    month_idx = MONTH_ORDER.get(str(record.month or "").strip().casefold(), 0)
    return (year, month_idx)


def _infer_direction(kpi_key: str, payload_directions: dict[str, str]) -> str:
    key_norm = str(kpi_key or "").strip().casefold()
    if key_norm in payload_directions:
        return payload_directions[key_norm]
    if any(tok in key_norm for tok in _LOWER_BETTER_TOKENS):
        return "lower_better"
    return "higher_better"


def _extract_payload_directions(record: PerformanceRecord) -> dict[str, str]:
    payload = record.record_payload if isinstance(record.record_payload, dict) else {}
    directions: dict[str, str] = {}
    kpi_meta = payload.get("kpi_metadata") or payload.get("kpis") or {}
    if isinstance(kpi_meta, dict):
        for k, v in kpi_meta.items():
            if isinstance(v, dict) and v.get("direction"):
                directions[str(k).strip().casefold()] = str(v["direction"]).strip()
    return directions


def _humanize_kpi_key(kpi_key: str) -> str:
    return str(kpi_key or "").replace("_", " ").strip().title() or "KPI"


class Agent360Service:
    """Assembles a zero-LLM 360° profile and deterministic What-If projections."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _load_latest_kpis(self, latest: PerformanceRecord) -> list[dict[str, Any]]:
        rows = (
            self.db.query(KPIValue)
            .filter(
                KPIValue.record_id == latest.id,
                KPIValue.record_year == latest.year,
            )
            .all()
        )
        if not isinstance(rows, list):
            return []
        directions = _extract_payload_directions(latest)
        items: list[dict[str, Any]] = []
        for row in rows:
            if not hasattr(row, "kpi_key") or not isinstance(row.kpi_key, str):
                continue
            actual = float(row.actual_value) if row.actual_value is not None else 0.0
            target = float(row.target_value) if row.target_value is not None else 0.0
            ach = float(row.achievement_ratio) if row.achievement_ratio is not None else 0.0
            weight = float(row.weight_applied) if row.weight_applied is not None else 0.0
            # Normalize achievement ratio to 0-100 score percentage for display
            ach_pct = round(ach * 100.0, 2) if ach <= 2.0 else round(ach, 2)
            direction = _infer_direction(row.kpi_key, directions)
            items.append(
                {
                    "kpi_key": row.kpi_key,
                    "name": _humanize_kpi_key(row.kpi_key),
                    "score": ach_pct,
                    "actual": round(actual, 4),
                    "target": round(target, 4),
                    "weight": round(weight, 4),
                    "achievement": round(ach, 4),
                    "direction": direction,
                    "grade": letter_grade(ach_pct),
                }
            )
        items.sort(key=lambda item: (item["weight"], item["score"]), reverse=True)
        return items

    def _to_kpi_inputs(self, kpi_scores: list[dict[str, Any]]) -> list[KpiInput]:
        inputs: list[KpiInput] = []
        for item in kpi_scores:
            if item.get("target") is None or item.get("weight") is None:
                continue
            target = float(item["target"])
            weight = float(item["weight"])
            if target <= 0 or weight <= 0:
                continue
            inputs.append(
                KpiInput(
                    name=str(item["name"]),
                    actual=float(item.get("actual") or 0.0),
                    target=target,
                    weight=weight,
                    direction=str(item.get("direction") or "higher_better"),
                )
            )
        return inputs

    def _assert_employee_in_scope(self, emp: Employee, scope: dict[str, Any] | None) -> None:
        """Enforce team RBAC for scoped managers viewing direct reports."""
        if not isinstance(scope, dict):
            return
        if scope.get("has_unrestricted_team_access"):
            return
        role = str(scope.get("role") or "")
        if role in ("Admin", "General Manager", "Performance Team", "Executive"):
            return
        caller_emp = str(scope.get("employee_id") or "").strip()
        if caller_emp and caller_emp.casefold() == str(emp.employee_id or "").casefold():
            return
        if scope.get("is_self_only"):
            raise PermissionError("Self-only users can only view their own 360° profile.")
        accessible = {str(t).strip().casefold() for t in (scope.get("accessible_teams") or []) if str(t).strip()}
        if not accessible:
            return
        team_name = None
        if getattr(emp, "team", None) is not None:
            team_name = getattr(emp.team, "name", None) or getattr(emp.team, "display_name", None)
        if not team_name and getattr(emp, "team_id", None) is not None:
            team_row = self.db.query(Team).filter(Team.id == emp.team_id).first()
            if team_row is not None:
                team_name = team_row.name or team_row.display_name
        if team_name and str(team_name).strip().casefold() not in accessible:
            raise PermissionError("You are not authorized to view this employee's 360° profile.")

    def list_authorized_employees(self, scope: dict[str, Any], *, limit: int = 50) -> list[dict[str, Any]]:
        """List bounded authorized employees for Managers/Admins to inspect 360° profiles."""
        if scope.get("is_self_only") or str(scope.get("role") or "") in ("Agent", "Employee"):
            return []
        try:
            q = (
                self.db.query(Employee, Team.name.label("team_name"))
                .outerjoin(Team, Team.id == Employee.team_id)
                .filter(Employee.is_active.is_(True))
            )
            role = str(scope.get("role") or "")
            if not scope.get("has_unrestricted_team_access") and role not in (
                "Admin",
                "General Manager",
                "Performance Team",
                "Executive",
            ):
                accessible = [str(t).strip() for t in (scope.get("accessible_teams") or []) if str(t).strip()]
                if not accessible:
                    return []
                q = q.filter(Team.name.in_(accessible))
            rows = q.order_by(Employee.name.asc()).limit(max(1, min(limit, 100))).all()
            return [
                {
                    "employee_code": str(emp.employee_id),
                    "employee_name": str(emp.name),
                    "team": str(team_name or ""),
                    "position": str(emp.position_name or ""),
                }
                for emp, team_name in rows
            ]
        except Exception:
            return []

    def get_agent_360(self, employee_code: str, scope: dict[str, Any]) -> dict[str, Any] | None:
        """Build the Agent 360° profile from canonical tables and services."""
        emp = (
            self.db.query(Employee)
            .filter(Employee.employee_id == employee_code, Employee.is_active.is_(True))
            .first()
        )
        if emp is None:
            return None
        self._assert_employee_in_scope(emp, scope)

        records = (
            self.db.query(PerformanceRecord)
            .filter(PerformanceRecord.employee_id == emp.id)
            .order_by(PerformanceRecord.year, PerformanceRecord.month)
            .all()
        )
        if not isinstance(records, list):
            records = list(records or [])
        records.sort(key=_month_sort_key)

        if not records:
            return {
                "employee_code": employee_code,
                "employee_name": emp.name,
                "current_period": None,
                "overall_score": None,
                "overall_grade": None,
                "score_trend": [],
                "kpi_scores": [],
                "top_strength": None,
                "top_opportunity": None,
                "active_corrective_actions": 0,
                "corrective_action_summary": None,
                "performance_classification": "New",
                "cohort": None,
                "what_if_suggestions": [],
                "message": "No performance records found yet.",
            }

        latest = records[-1]
        current_period = f"{latest.month} {latest.year}"

        recent = records[-6:]
        score_trend = [
            {
                "month": r.month,
                "year": int(r.year),
                "score": float(r.score) if r.score is not None else None,
                "grade": r.grade,
            }
            for r in recent
        ]

        # Real per-KPI breakdown from KPIValue rows; fallback to overall only if none exist
        kpi_scores = self._load_latest_kpis(latest)
        if not kpi_scores:
            kpi_scores = [
                {
                    "kpi_key": "overall",
                    "name": "Overall",
                    "score": float(latest.score) if latest.score is not None else None,
                    "actual": float(latest.score) if latest.score is not None else None,
                    "target": 100.0,
                    "weight": 1.0,
                    "achievement": (float(latest.score) / 100.0) if latest.score is not None else 0.0,
                    "direction": "higher_better",
                    "grade": latest.grade,
                    "status": latest.status,
                }
            ]

        scored_kpis = [k for k in kpi_scores if k.get("score") is not None]
        if len(scored_kpis) >= 2:
            best = max(scored_kpis, key=lambda k: (k["score"], k.get("weight") or 0.0))
            worst = min(scored_kpis, key=lambda k: (k["score"], -(k.get("weight") or 0.0)))
            top_strength = str(best["name"])
            top_opportunity = str(worst["name"]) if worst["name"] != best["name"] else None
        else:
            top_strength = "Overall performance" if (latest.score or 0) >= 80 else None
            top_opportunity = "Overall performance" if (latest.score or 0) < 80 else None

        # Corrective actions
        try:
            history = CorrectiveActionService(self.db).get_history(employee_code, scope)
            active_count = sum(
                1 for h in (history or []) if str(h.get("status") or "").casefold() in {"open", "in_progress", "in progress"}
            )
            ca_summary = f"{active_count} active corrective action(s)" if active_count else None
        except Exception:
            active_count = 0
            ca_summary = None

        # Performance classification
        if len(records) >= 2:
            prev_score = float(records[-2].score) if records[-2].score is not None else 0.0
            curr_score = float(latest.score) if latest.score is not None else 0.0
            if curr_score > prev_score + 2.0:
                classification = "Improving"
            elif curr_score < prev_score - 2.0:
                classification = "Declining"
            else:
                classification = "Stable"
        else:
            classification = "New"

        cohort = self._compute_cohort(emp, latest)

        # Real What-If suggestions on top 2 opportunity KPIs
        what_if: list[dict[str, Any]] = []
        kpi_inputs = self._to_kpi_inputs(kpi_scores)
        if kpi_inputs:
            opportunity_kpis = sorted(
                [k for k in kpi_scores if (k.get("achievement") or 0.0) < 1.0 and (k.get("weight") or 0.0) > 0],
                key=lambda k: ((k.get("achievement") or 0.0), -(k.get("weight") or 0.0)),
            )[:2]
            for opp in opportunity_kpis:
                target_val = float(opp.get("target") or 0.0)
                step = round(max(target_val * 0.05, 1.0), 2) if target_val > 1.0 else round(max(target_val * 0.05, 0.05), 3)
                sim = simulate_kpi_improvement(kpi_inputs, str(opp["name"]), step)
                if sim is not None and sim.score_delta > 0:
                    verb = "Reduce" if opp.get("direction") == "lower_better" else "Improve"
                    what_if.append(
                        {
                            "kpi_name": opp["name"],
                            "current_value": opp.get("actual"),
                            "improvement_step": step,
                            "projected_score": sim.projected_score,
                            "projected_grade": sim.projected_grade,
                            "score_delta": sim.score_delta,
                            "suggestion": f"{verb} {opp['name']} by {step} to lift score by +{sim.score_delta:.1f} pts (Grade {sim.projected_grade})",
                        }
                    )
        if not what_if and latest.score is not None and float(latest.score) < 95.0:
            what_if.append(
                {
                    "kpi_name": top_opportunity or "Overall Score",
                    "current_value": float(latest.score),
                    "suggestion": "Improve your lowest KPI by 5% to see projected score and grade lift",
                }
            )

        return {
            "employee_code": employee_code,
            "employee_name": emp.name,
            "current_period": current_period,
            "overall_score": float(latest.score) if latest.score is not None else None,
            "overall_grade": latest.grade,
            "score_trend": score_trend,
            "kpi_scores": kpi_scores,
            "top_strength": top_strength,
            "top_opportunity": top_opportunity,
            "active_corrective_actions": active_count,
            "corrective_action_summary": ca_summary,
            "performance_classification": classification,
            "cohort": cohort,
            "what_if_suggestions": what_if,
        }

    def simulate_what_if(
        self,
        employee_code: str,
        kpi_name: str,
        improvement_pct: float,
        scope: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Run deterministic What-If simulation against the employee's latest KPI values."""
        emp = (
            self.db.query(Employee)
            .filter(Employee.employee_id == employee_code, Employee.is_active.is_(True))
            .first()
        )
        if emp is None:
            return None
        self._assert_employee_in_scope(emp, scope)
        records = (
            self.db.query(PerformanceRecord)
            .filter(PerformanceRecord.employee_id == emp.id)
            .all()
        )
        if not records:
            return None
        records.sort(key=_month_sort_key)
        latest = records[-1]
        kpi_scores = self._load_latest_kpis(latest)
        kpi_inputs = self._to_kpi_inputs(kpi_scores)
        if not kpi_inputs:
            return None

        # Allow matching by display name or raw kpi_key
        resolved_name = kpi_name
        for item in kpi_scores:
            if (
                str(item.get("kpi_key") or "").casefold() == kpi_name.casefold()
                or str(item.get("name") or "").casefold() == kpi_name.casefold()
            ):
                resolved_name = str(item["name"])
                break

        result = simulate_kpi_improvement(kpi_inputs, resolved_name, improvement_pct)
        if result is None:
            return None
        return {
            "employee_code": employee_code,
            "period": f"{latest.month} {latest.year}",
            "kpi_name": result.kpi_name,
            "improvement_pct": result.improvement_pct,
            "current_score": result.current_score,
            "projected_score": result.projected_score,
            "current_grade": result.current_grade,
            "projected_grade": result.projected_grade,
            "score_delta": result.score_delta,
            "current_achievement": result.current_achievement,
            "projected_achievement": result.projected_achievement,
            "capped": result.capped,
        }

    def _compute_cohort(self, emp: Employee, latest: PerformanceRecord) -> dict[str, Any] | None:
        """Compute privacy-safe cohort benchmark (N >= 5, no min/max/exact rank)."""
        try:
            position = latest.position_name or emp.position_name
            filters = [
                PerformanceRecord.month == latest.month,
                PerformanceRecord.year == latest.year,
                PerformanceRecord.performance_level == latest.performance_level,
            ]
            if position:
                filters.append(PerformanceRecord.position_name == position)
            if latest.branch_key:
                filters.append(PerformanceRecord.branch_key == latest.branch_key)
            else:
                filters.append(Employee.region == emp.region)

            agg = (
                self.db.query(
                    sqlfunc.count(PerformanceRecord.id).label("cnt"),
                    sqlfunc.avg(PerformanceRecord.score).label("avg_score"),
                )
                .join(Employee, Employee.id == PerformanceRecord.employee_id)
                .filter(*filters)
                .having(sqlfunc.count(PerformanceRecord.id) >= MIN_COHORT_SIZE)
                .first()
            )
            if agg is None or not agg.cnt or int(agg.cnt) < MIN_COHORT_SIZE:
                return None

            cnt = int(agg.cnt)
            avg = float(agg.avg_score) if agg.avg_score is not None else 0.0
            my_score = float(latest.score) if latest.score is not None else 0.0

            # Compute SQL-backed percentile band without returning rank/min/max
            higher_count = (
                self.db.query(sqlfunc.count(PerformanceRecord.id))
                .join(Employee, Employee.id == PerformanceRecord.employee_id)
                .filter(*filters, PerformanceRecord.score > my_score)
                .scalar()
                or 0
            )
            top_fraction = (int(higher_count) + 1) / float(cnt)
            if top_fraction <= 0.10:
                band = "Top 10%"
            elif top_fraction <= 0.25:
                band = "Top 25%"
            elif top_fraction <= 0.50:
                band = "Top 50%"
            else:
                band = "Bottom 50%"

            return {
                "cohort_size": cnt,
                "cohort_avg_score": round(avg, 1),
                "percentile_band": band,
            }
        except Exception:
            return None
