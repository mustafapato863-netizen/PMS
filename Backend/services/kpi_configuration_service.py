from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from config.loader import iter_employee_kpi_configs, load_all_team_configs
from repositories.kpi_configuration_repository import KPIConfigurationRepository
from services.planning_service import MONTH_ORDER


class KPIConfigurationService:
    """Canonical, deployment-safe KPI configuration projection.

    Team configuration files define the scoring model used by ingestion. Exact
    target values come from the persisted KPI evidence because targets may be
    supplied by the workbook and may change by period or position.
    """

    def __init__(self, db: Session):
        self.targets = KPIConfigurationRepository(db)

    @staticmethod
    def _scoped_weights() -> dict[str, dict[str, dict[str, float]]]:
        result: dict[str, dict[str, dict[str, float]]] = {}
        for config in load_all_team_configs():
            team = str(config["team"])
            scopes: dict[str, dict[str, float]] = defaultdict(dict)
            for position, _display_order, kpi in iter_employee_kpi_configs(config):
                scopes[str(position or "")][str(kpi["key"])] = float(kpi["weight"])
            result[team] = dict(scopes)
        return result

    @staticmethod
    def _flat_if_unambiguous(scopes: dict[str, dict[str, float]]) -> dict[str, float]:
        if not scopes:
            return {}
        if len(scopes) == 1:
            return dict(next(iter(scopes.values())))

        values_by_key: dict[str, set[float]] = defaultdict(set)
        occurrences: dict[str, int] = defaultdict(int)
        for weights in scopes.values():
            for key, value in weights.items():
                values_by_key[key].add(value)
                occurrences[key] += 1
        return {
            key: next(iter(values))
            for key, values in values_by_key.items()
            if len(values) == 1 and occurrences[key] == len(scopes)
        }

    def list_weights(self) -> list[dict[str, Any]]:
        return [
            {
                "team": team,
                "weights": self._flat_if_unambiguous(scopes),
                "scopes": [
                    {"position": position or None, "weights": weights}
                    for position, weights in sorted(scopes.items())
                ],
            }
            for team, scopes in sorted(self._scoped_weights().items())
        ]

    def list_targets(self) -> list[dict[str, Any]]:
        latest: dict[tuple[str, str, str], tuple[tuple[int, int], float]] = {}
        for team, position, key, year, month, target in self.targets.list_distinct_employee_targets():
            period = (year, MONTH_ORDER.get(month, 0))
            scoped_key = (team, position, key)
            if scoped_key not in latest or period > latest[scoped_key][0]:
                latest[scoped_key] = (period, target)

        grouped: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
        for (team, position, key), (_period, target) in latest.items():
            grouped[team][position][key] = target

        known_teams = set(self._scoped_weights()) | set(grouped)
        return [
            {
                "team": team,
                "targets": self._flat_if_unambiguous(grouped.get(team, {})),
                "scopes": [
                    {"position": position or None, "targets": targets}
                    for position, targets in sorted(grouped.get(team, {}).items())
                ],
            }
            for team in sorted(known_teams)
        ]
