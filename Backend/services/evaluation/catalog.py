"""Build the scoring catalog from database teams, file templates, and importers."""

from __future__ import annotations

from sqlalchemy.orm import Session

from config.loader import get_configured_performance_levels, iter_employee_kpi_configs, load_all_team_configs
from data_cleaning.cleaner_factory import CleanerFactory
from models.models import EvaluationScope, Team
from services.evaluation.capabilities import CapabilityDecision, decide
from services.evaluation.scoring import SUPPORTED_DIRECTIONS
from utils.performance_levels import PERFORMANCE_LEVELS
from utils.team_identity import logical_team_name

HISTORY_NOTE = (
    "Historical direction and formulas are not stored on older results. "
    "Those scores stay as saved until an explicit apply. Missing history is listed, not guessed."
)


def _norm(value: str) -> str:
    return str(value or "").casefold().replace(" ", "_").replace("-", "_").replace("preapprovals", "pre_approvals")


def _display_and_config(team: Team, file_by_key: dict) -> tuple[str, dict | None]:
    for key in (_norm(logical_team_name(team)), _norm(team.name), _norm(getattr(team, "db_name", ""))):
        config = file_by_key.get(key)
        if config is not None:
            display = str(config.get("team") or config.get("db_name") or logical_team_name(team))
            return display, config
    return logical_team_name(team), None


def _importer_names() -> set[str]:
    try:
        return {_norm(name) for name in CleanerFactory.get_available_teams()}
    except Exception:
        return set()


def _kpis_for(config: dict, level: str, position: str) -> list[dict]:
    if level == "Employee":
        rows = []
        for found_position, _order, kpi in iter_employee_kpi_configs(config):
            if (found_position or "") == (position or ""):
                rows.append(kpi)
        if rows:
            return rows
        if not position:
            return [kpi for kpi in config.get("kpis", []) if isinstance(kpi, dict)]
        return []
    level_config = (config.get("performance_levels") or {}).get(level) or {}
    if position:
        position_config = (level_config.get("positions") or {}).get(position) or {}
        return [kpi for kpi in position_config.get("kpis", []) if isinstance(kpi, dict)]
    return [kpi for kpi in level_config.get("kpis", []) if isinstance(kpi, dict)]


def _positions(config: dict, level: str) -> list[str]:
    if level == "Employee":
        found = []
        seen = set()
        for position, _order, _kpi in iter_employee_kpi_configs(config):
            name = position or ""
            if name not in seen:
                seen.add(name)
                found.append(name)
        if found:
            return found
        return [""] if config.get("kpis") else []
    level_config = (config.get("performance_levels") or {}).get(level) or {}
    names = [""] if level_config.get("kpis") else []
    names.extend(str(name) for name in (level_config.get("positions") or {}))
    return names or [""]


def classify_readiness(
    *,
    has_team: bool,
    team_active: bool,
    has_config: bool,
    has_kpis: bool,
    ambiguous: list[str],
    employee_importer: bool,
) -> tuple[str, str | None]:
    """Classify one scope. Missing history and unknown directions stay listed, not guessed."""
    if not has_team:
        return (
            "unlinked_baseline",
            "File baseline has no live team row. It is not a configured live team.",
        )
    if not team_active:
        return (
            "blocked",
            "This team is inactive. It stays in the catalog for history and is outside the supported rollout.",
        )
    if not has_config or not has_kpis:
        return (
            "blocked",
            "No technical baseline is checked in for this team and level. It stays outside the supported rollout.",
        )
    if ambiguous:
        return (
            "blocked",
            "KPI direction is not a supported higher-is-better or lower-is-better policy: " + ", ".join(ambiguous),
        )
    if not employee_importer:
        return (
            "blocked",
            "No supported importer is registered for this team and level. The scope stays blocked.",
        )
    return "supported", None


def _importer_registered(names: list[str], importers: set[str]) -> bool:
    return any(_norm(name) in importers for name in names if name)


def calculation_for(display: str, level: str, position: str, config: dict | None, importers: set[str] | None = None) -> CapabilityDecision:
    """Live file-and-importer decision. This does not read or write catalog rows."""
    registered_importers = _importer_names() if importers is None else importers
    names = [display]
    if config is not None:
        names.extend([config.get("team"), config.get("db_name")])
    kpis = _kpis_for(config, level, position) if config else []
    return decide(
        team_name=display,
        level=level,
        position=position or "",
        kpis=kpis,
        importer_registered=_importer_registered(names, registered_importers),
    )


def _baseline_lines(config: dict, level: str, position: str) -> list[dict]:
    lines = []
    for kpi in _kpis_for(config, level, position):
        lines.append(
            {
                "kpi_key": str(kpi.get("key") or ""),
                "label": kpi.get("label") or kpi.get("key"),
                "weight": float(kpi.get("weight") or 0),
                "direction": kpi.get("direction"),
                "target": None,
                "target_mode": "workbook",
                "unit": kpi.get("unit") or "%",
            }
        )
    return [line for line in lines if line["kpi_key"]]


class EvaluationCatalog:
    def __init__(self, db: Session):
        self.db = db

    def sync(self) -> list[EvaluationScope]:
        files = []
        try:
            files = load_all_team_configs()
        except Exception:
            files = []
        file_by_key = {}
        for config in files:
            keys = {_norm(config.get("team") or ""), _norm(config.get("db_name") or "")}
            keys.discard("")
            for key in keys:
                file_by_key[key] = config
        self._file_by_key = file_by_key

        teams = self.db.query(Team).all()
        team_by_key: dict[str, Team] = {}
        for team in teams:
            for key in {_norm(logical_team_name(team)), _norm(team.name), _norm(team.db_name)}:
                if key:
                    team_by_key.setdefault(key, team)

        importers = _importer_names()
        seen: set[tuple[str, str, str]] = set()
        wanted: list[dict] = []

        def add(display: str, level: str, position: str, team: Team | None, config: dict | None, source: str) -> None:
            identity = (display.casefold(), level, position or "")
            if identity in seen:
                return
            seen.add(identity)
            kpis = _kpis_for(config, level, position) if config else []
            ambiguous = sorted(
                {
                    str(kpi.get("key"))
                    for kpi in kpis
                    if str(kpi.get("direction") or "") not in SUPPORTED_DIRECTIONS
                }
            )
            names = [part for part in (display, getattr(team, "name", None), getattr(team, "db_name", None), (config or {}).get("db_name"), (config or {}).get("team")) if part]
            importer = next((name for name in names if _norm(name) in importers), None)
            employee_importer = level == "Employee" and importer is not None
            readiness, reason = classify_readiness(
                has_team=team is not None,
                team_active=bool(team.is_active) if team is not None else False,
                has_config=config is not None,
                has_kpis=bool(kpis),
                ambiguous=ambiguous,
                employee_importer=employee_importer,
            )
            decision = calculation_for(display, level, position, config, importers)
            if readiness == "supported" and not decision.allows_ratio_edit:
                readiness = "blocked"
                reason = decision.reason
            wanted.append(
                {
                    "team": team,
                    "team_key": display.casefold(),
                    "display_name": display,
                    "performance_level": level,
                    "position_name": position or "",
                    "readiness": readiness,
                    "block_reason": reason,
                    "ambiguous_kpis": ambiguous,
                    "importer_name": importer if employee_importer else None,
                    "source_kind": source,
                    "lines": _baseline_lines(config, level, position) if config else [],
                    "thresholds": (config or {}).get("grade_thresholds") or {"A": 95, "B": 85, "C": 75, "D": 65},
                    "decision": decision,
                }
            )

        for config in files:
            display = str(config.get("team") or config.get("db_name") or "Unknown")
            team = team_by_key.get(_norm(display)) or team_by_key.get(_norm(config.get("db_name") or ""))
            source = "both" if team is not None else "file"
            for level in get_configured_performance_levels(config):
                for position in _positions(config, level):
                    add(display, level, position, team, config, source)

        for team in teams:
            display, config = _display_and_config(team, file_by_key)
            source = "both" if config is not None else "database"
            for level in PERFORMANCE_LEVELS:
                if any(item[0] == display.casefold() and item[1] == level for item in seen):
                    continue
                add(display, level, "", team, config, source)

        existing = {
            (row.team_key, row.performance_level, row.position_name): row
            for row in self.db.query(EvaluationScope).all()
        }
        kept = set()
        rows = []
        for item in wanted:
            key = (item["team_key"], item["performance_level"], item["position_name"])
            kept.add(key)
            row = existing.get(key)
            if row is None:
                row = EvaluationScope(team_key=item["team_key"], performance_level=item["performance_level"], position_name=item["position_name"], history_note=HISTORY_NOTE)
                self.db.add(row)
            row.team_id = item["team"].id if item["team"] is not None else None
            row.display_name = item["display_name"]
            row.readiness = item["readiness"]
            row.block_reason = item["block_reason"]
            row.history_note = HISTORY_NOTE
            row.ambiguous_kpis = item["ambiguous_kpis"]
            row.importer_name = item["importer_name"]
            row.policy_family = "employee_ratio" if item["readiness"] == "supported" else "unsupported"
            row.source_kind = item["source_kind"]
            rows.append(row)
        for key, row in existing.items():
            if key not in kept:
                row.readiness = "blocked"
                row.block_reason = "This scope is no longer in the live team or file catalog."
                rows.append(row)
        self.db.flush()
        self.db.commit()
        self._baselines = {(row.team_key, row.performance_level, row.position_name): item["lines"] for item, row in zip(wanted, rows[: len(wanted)])}
        self._thresholds = {(row.team_key, row.performance_level, row.position_name): item["thresholds"] for item, row in zip(wanted, rows[: len(wanted)])}
        self._decisions = {(row.team_key, row.performance_level, row.position_name): item["decision"] for item, row in zip(wanted, rows[: len(wanted)])}
        return rows

    def baseline_lines(self, scope: EvaluationScope) -> list[dict]:
        if not hasattr(self, "_baselines"):
            self.sync()
        return list(self._baselines.get((scope.team_key, scope.performance_level, scope.position_name), []))

    def thresholds(self, scope: EvaluationScope) -> dict:
        if not hasattr(self, "_thresholds"):
            self.sync()
        return dict(self._thresholds.get((scope.team_key, scope.performance_level, scope.position_name), {"A": 95, "B": 85, "C": 75, "D": 65}))

    def decision_for(self, scope: EvaluationScope) -> CapabilityDecision:
        """Recompute capability from files. Stored readiness and client flags are ignored."""
        cached = getattr(self, "_decisions", {}).get((scope.team_key, scope.performance_level, scope.position_name))
        if isinstance(cached, CapabilityDecision):
            return cached
        config = self._config_for(scope.display_name)
        return calculation_for(scope.display_name, scope.performance_level, scope.position_name or "", config)

    def _config_for(self, display: str) -> dict | None:
        if not hasattr(self, "_file_by_key"):
            files = []
            try:
                files = load_all_team_configs()
            except Exception:
                files = []
            file_by_key = {}
            for config in files:
                for key in (_norm(config.get("team") or ""), _norm(config.get("db_name") or "")):
                    if key:
                        file_by_key[key] = config
            self._file_by_key = file_by_key
        return self._file_by_key.get(_norm(display))

    def serialize(self, scope: EvaluationScope) -> dict:
        decision = self.decision_for(scope)
        enabled = scope.readiness == "supported" and decision.allows_ratio_edit
        return {
            "id": str(scope.id),
            "team_id": str(scope.team_id) if scope.team_id else None,
            "team_key": scope.team_key,
            "display_name": scope.display_name,
            "performance_level": scope.performance_level,
            "position_name": scope.position_name,
            "readiness": scope.readiness,
            "block_reason": scope.block_reason,
            "history_note": scope.history_note,
            "ambiguous_kpis": list(scope.ambiguous_kpis or []),
            "importer_name": scope.importer_name,
            "policy_family": scope.policy_family,
            "source_kind": scope.source_kind,
            "supported": enabled,
            "edit_mode": "full" if enabled else "blocked",
            "weight_only_allowed": False,
            "capability_reason": decision.reason if enabled else (scope.block_reason or decision.reason),
        }
