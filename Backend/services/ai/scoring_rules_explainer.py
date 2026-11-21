"""On-demand scoring rules explainer for the AI assistant.

Returns scoring rules, weights, targets, and grade thresholds from the
CANONICAL sources (never the legacy GradeThreshold table):
- utils.scoring_rules.GRADE_THRESHOLD_MAP / letter_grade
- config.loader.GLOBAL_KPI_ACHIEVEMENT_CAP
- KPIConfigurationService.list_weights() / list_targets()
- scoring engine direction/formula descriptions

Output is bounded (≤ 500 tokens) for LLM context.
"""

from __future__ import annotations

from typing import Any

from config.loader import GLOBAL_KPI_ACHIEVEMENT_CAP
from services.evaluation.scoring import SUPPORTED_DIRECTIONS
from utils.scoring_rules import GRADE_THRESHOLD_MAP


class ScoreRulesExplainer:
    def __init__(self, db=None) -> None:
        self.db = db

    def explain(
        self,
        passport,
        kpi_name: str | None = None,
    ) -> dict[str, Any]:
        """Return applicable scoring rules for the caller's scope."""
        result: dict[str, Any] = {
            "grade_thresholds": dict(GRADE_THRESHOLD_MAP),
            "achievement_cap": GLOBAL_KPI_ACHIEVEMENT_CAP,
            "supported_directions": sorted(SUPPORTED_DIRECTIONS),
            "formula": "higher_better: actual/target; lower_better: target/actual; capped at 1.0",
            "scale_rule": "Stored score in (0,1] is a ratio x100; above 1 used as-is.",
        }

        # Weights + targets from canonical config service, scoped to authorized teams
        if self.db is not None:
            try:
                from services.kpi_configuration_service import KPIConfigurationService

                cfg = KPIConfigurationService(self.db)
                weights = cfg.list_weights()
                targets = cfg.list_targets()
                authorized = set(getattr(passport, "authorized_teams", []) or [])

                def scope_filter(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
                    if getattr(passport, "has_unrestricted_team_access", False):
                        return items
                    return [i for i in items if str(i.get("team") or "") in authorized]

                result["weights"] = scope_filter(weights)[:5]
                result["targets"] = scope_filter(targets)[:5]
            except Exception:
                result["weights"] = []
                result["targets"] = []
        else:
            result["weights"] = []
            result["targets"] = []

        if kpi_name:
            result["kpi_filter"] = kpi_name
        return result

    def to_xml(self, passport, kpi_name: str | None = None) -> str:
        """Serialize rules as compact XML (bounded)."""
        data = self.explain(passport, kpi_name)
        grades = ",".join(f"{k}:{v}" for k, v in data["grade_thresholds"].items())
        return (
            "<AUTHORIZED_SCORING_RULES>"
            f"grades=[{grades}] cap={data['achievement_cap']} "
            f"formula='{data['formula']}' "
            f"directions={data['supported_directions']}"
            "</AUTHORIZED_SCORING_RULES>"
        )
