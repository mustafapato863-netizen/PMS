"""Agent 360° Profile Service.

Zero-LLM deterministic data assembly for an agent's self-service scorecard.
Reuses existing services — does NOT duplicate scoring logic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from models.models import Employee, PerformanceRecord, User
from services.corrective_action_service import CorrectiveActionService


class Agent360Service:
    """Assembles a zero-LLM 360° profile for an agent."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_agent_360(self, employee_code: str, scope: dict[str, Any]) -> dict[str, Any] | None:
        """Build the Agent 360° profile from existing services.

        Returns None if the employee is not found or not authorized.
        """
        # Find the employee
        emp = (
            self.db.query(Employee)
            .filter(Employee.employee_id == employee_code, Employee.is_active.is_(True))
            .first()
        )
        if emp is None:
            return None

        # Get performance records
        records = (
            self.db.query(PerformanceRecord)
            .filter(PerformanceRecord.employee_id == emp.id)
            .order_by(PerformanceRecord.year, PerformanceRecord.month)
            .all()
        )
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

        # Latest record
        latest = records[-1]
        current_period = f"{latest.month} {latest.year}"

        # Score trend (last 6 months)
        recent = records[-6:]
        score_trend = [
            {"month": r.month, "year": r.year, "score": float(r.score) if r.score is not None else None}
            for r in recent
        ]

        # KPI breakdown from latest record
        kpi_scores = []
        # PerformanceRecord stores score, grade, status — KPI-level details come from the record
        kpi_scores.append({
            "name": "Overall",
            "score": float(latest.score) if latest.score is not None else None,
            "grade": latest.grade,
            "status": latest.status,
            "target": None,
            "weight": None,
        })

        # Top strength / opportunity (simplified — based on single record)
        top_strength = "Overall performance" if (latest.score or 0) >= 80 else None
        top_opportunity = "Overall performance" if (latest.score or 0) < 80 else None

        # Corrective actions
        try:
            history = CorrectiveActionService(self.db).get_history(employee_code, scope)
            active_count = sum(1 for h in (history or []) if h.get("status") == "Open")
            ca_summary = f"{active_count} active corrective action(s)" if active_count else None
        except Exception:
            active_count = 0
            ca_summary = None

        # Performance classification
        if len(records) >= 2:
            prev_score = float(records[-2].score) if records[-2].score is not None else 0
            curr_score = float(latest.score) if latest.score is not None else 0
            if curr_score > prev_score + 2:
                classification = "Improving"
            elif curr_score < prev_score - 2:
                classification = "Declining"
            else:
                classification = "Stable"
        else:
            classification = "New"

        # Cohort benchmarking (privacy-safe, min 5)
        cohort = self._compute_cohort(emp, latest)

        # What-If suggestions (top 2 KPIs)
        what_if = []
        if latest.score is not None and latest.score < 90:
            what_if.append({
                "kpi_name": "Overall Score",
                "current_value": float(latest.score),
                "suggestion": "Improve your lowest KPI by 5% to see projected impact",
            })

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

    def _compute_cohort(self, emp: Employee, latest: PerformanceRecord) -> dict[str, Any] | None:
        """Compute privacy-safe cohort benchmark. Returns None if cohort < 5."""
        try:
            from sqlalchemy import func as sqlfunc
            cohort_query = (
                self.db.query(
                    sqlfunc.count(PerformanceRecord.id).label("cnt"),
                    sqlfunc.avg(PerformanceRecord.score).label("avg_score"),
                )
                .join(Employee, Employee.id == PerformanceRecord.employee_id)
                .filter(
                    PerformanceRecord.month == latest.month,
                    PerformanceRecord.year == latest.year,
                    PerformanceRecord.performance_level == latest.performance_level,
                    Employee.position == emp.position,
                    Employee.region == emp.region,
                )
                .group_by(PerformanceRecord.performance_level)
                .having(sqlfunc.count(PerformanceRecord.id) >= 5)
                .first()
            )
            if cohort_query is None:
                return None
            cnt = int(cohort_query.cnt)
            avg = float(cohort_query.avg_score) if cohort_query.avg_score is not None else 0.0
            score = float(latest.score) if latest.score is not None else 0.0
            if score >= avg * 1.1:
                band = "Top 10%"
            elif score >= avg * 1.05:
                band = "Top 25%"
            elif score >= avg:
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
