"""Build the scoring catalog from database teams, file templates, and importers.

Callable contract for the workflow consumer. Omit ``year`` and ``month`` and
every call keeps today's conservative result: Coding Employee and Submission
Employee can be supported, Outbound stays blocked, and no month is inferred.

.. code-block:: python

    decision = catalog.decision_for(scope)
    decision = catalog.decision_for(scope, year, month)
    lines = catalog.baseline_lines(scope)
    lines = catalog.baseline_lines(scope, year, month)
    body = catalog.serialize(scope)
    body = catalog.serialize(scope, year, month)
    reconciled = catalog.reconcile_period_lines(scope, year, month, copied_lines)
    decision = calculation_for(display, level, position, config, importers, year, month)

``decision_for`` recomputes from the checked-in file and, when both period
arguments are passed, from ``period_capability``. Passing only ``year`` or only
``month`` stays conservative for Outbound. Stored readiness and client flags
are ignored. ``baseline_lines`` without a period is the file template.
With a period, Outbound Employee uses the helper's exact-month lines (direction
``higher_better``, unit ``%``, ``target_mode`` ``workbook``, source targets)
plus the optional zero-weight AHT diagnostic. ``serialize`` without a period
keeps ``readiness``, ``supported``, and ``edit_mode`` blocked for Outbound and
adds ``period_dependent`` plus ``admitted_periods``. With both ``year`` and
``month``, those three top-level fields follow that exact month:
August 2026 is ``readiness="supported"`` and ``supported`` true, and a later
month stays blocked. ``global_readiness`` and ``global_supported`` keep the
no-period catalog result. The period body also adds ``period_readiness``,
``period_supported``, ``period_edit_mode``, ``lines``, and ``period``.

``reconcile_period_lines`` returns ``lines``, ``diagnostics``,
``template_changed``, ``preserved_values``, ``source_baseline``, ``blocked``,
``period_status``, and ``weights_total``. Same weighted keys keep the copied
targets and weights. A different set, including July copied into August, is
replaced by the canonical destination lines so the weights sum to 1 and
Productivity is visible instead of dropped.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from config.loader import get_configured_performance_levels, iter_employee_kpi_configs, load_all_team_configs
from data_cleaning.cleaner_factory import CleanerFactory
from models.models import EvaluationScope, Team
from services.evaluation.capabilities import (
    CapabilityDecision,
    admitted_outbound_periods,
    decide,
    is_outbound_employee_scope,
)
from services.evaluation.scoring import SUPPORTED_DIRECTIONS
from utils.performance_levels import PERFORMANCE_LEVELS
from utils.team_identity import logical_team_name

AHT_KEY = "AHT"

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


def calculation_for(
    display: str,
    level: str,
    position: str,
    config: dict | None,
    importers: set[str] | None = None,
    year: int | None = None,
    month: int | str | None = None,
) -> CapabilityDecision:
    """Live file-and-importer decision. This does not read or write catalog rows.

    ``year`` and ``month`` are optional and are forwarded to ``decide``. Omit
    them and Outbound stays blocked. Pass the exact period and only the helper's
    admitted Outbound Employee month can return ``edit_mode="full"``.
    """
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
        year=year,
        month=month,
    )


def _copy_line(line: dict) -> dict:
    return {
        "kpi_key": str(line.get("kpi_key") or ""),
        "label": line.get("label") or line.get("kpi_key"),
        "weight": float(line.get("weight") or 0),
        "direction": line.get("direction"),
        "target": line.get("target"),
        "target_mode": line.get("target_mode") or "workbook",
        "unit": line.get("unit") or "%",
    }


def _aht_diagnostic() -> dict:
    """Optional handle-time line. The real seeder keeps Outbound AHT at weight 0."""
    return {
        "kpi_key": AHT_KEY,
        "label": "AHT",
        "weight": 0.0,
        "direction": "lower_better",
        "target": None,
        "target_mode": "workbook",
        "unit": "min",
        "optional": True,
        "scored": False,
        "enabled": False,
    }


def _period_template(display: str, level: str, position: str, year, month) -> tuple[list[dict], dict] | None:
    """Exact-month Outbound lines, or None when this scope has no period template."""
    if year is None or month is None or not is_outbound_employee_scope(display, level, position):
        return None
    from services.outbound_period_basis import period_capability

    try:
        decision = period_capability(int(year), month)
    except (TypeError, ValueError):
        return None
    lines = []
    for raw in decision.get("lines") or []:
        line = _copy_line(raw)
        line["direction"] = raw.get("direction") or "higher_better"
        line["unit"] = raw.get("unit") or "%"
        line["target_mode"] = raw.get("target_mode") or "workbook"
        if raw.get("weight_key"):
            line["weight_key"] = raw.get("weight_key")
        lines.append(line)
    lines.append(_aht_diagnostic())
    return lines, decision


def _weighted_keys(lines: list[dict]) -> set[str]:
    found = set()
    for line in lines or []:
        key = str(line.get("kpi_key") or "")
        try:
            weight = float(line.get("weight") or 0)
        except (TypeError, ValueError):
            continue
        if key and weight > 0:
            found.add(key)
    return found


def _weight_total(lines: list[dict]) -> Decimal:
    total = Decimal("0")
    for line in lines or []:
        try:
            total += Decimal(str(line.get("weight") or 0))
        except Exception:
            continue
    return total


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

    def baseline_lines(self, scope: EvaluationScope, year: int | None = None, month: int | str | None = None) -> list[dict]:
        """File baseline, or the exact-month Outbound template when a period is passed.

        Without ``year`` and ``month`` the result is the checked-in file,
        including Outbound's four technical KPIs. With a period, Outbound
        Employee uses ``period_capability`` lines and does not copy August into
        a later month.
        """
        template = _period_template(scope.display_name, scope.performance_level, scope.position_name or "", year, month)
        if template is not None:
            return [dict(line) for line in template[0]]
        if not hasattr(self, "_baselines"):
            self.sync()
        return [dict(line) for line in self._baselines.get((scope.team_key, scope.performance_level, scope.position_name), [])]

    def thresholds(self, scope: EvaluationScope) -> dict:
        if not hasattr(self, "_thresholds"):
            self.sync()
        return dict(self._thresholds.get((scope.team_key, scope.performance_level, scope.position_name), {"A": 95, "B": 85, "C": 75, "D": 65}))

    def decision_for(self, scope: EvaluationScope, year: int | None = None, month: int | str | None = None) -> CapabilityDecision:
        """Recompute capability from files. Stored readiness and client flags are ignored.

        The cached sync decision is period-less. A caller that passes ``year``
        and ``month`` always recomputes so July 2026 can be admitted without
        marking September supported.
        """
        if year is None and month is None:
            cached = getattr(self, "_decisions", {}).get((scope.team_key, scope.performance_level, scope.position_name))
            if isinstance(cached, CapabilityDecision):
                return cached
        config = self._config_for(scope.display_name)
        return calculation_for(
            scope.display_name,
            scope.performance_level,
            scope.position_name or "",
            config,
            year=year,
            month=month,
        )

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

    def serialize(self, scope: EvaluationScope, year: int | None = None, month: int | str | None = None) -> dict:
        """Catalog row for the workflow consumer.

        Without a period, ``readiness``, ``supported``, and ``edit_mode`` follow
        stored readiness plus the period-less decision, so Outbound stays blocked.
        ``period_dependent`` is true only for Outbound Employee. With both a year
        and a month, those three top-level fields follow that exact month. The
        stored scope row is not rewritten. ``global_readiness`` and
        ``global_supported`` keep the no-period result.
        """
        periodless = self.decision_for(scope)
        has_period = year is not None and month is not None
        decision = self.decision_for(scope, year, month) if has_period else periodless
        if has_period:
            enabled = decision.allows_ratio_edit
            readiness = "supported" if enabled else "blocked"
        else:
            enabled = scope.readiness == "supported" and decision.allows_ratio_edit
            readiness = scope.readiness
        period_dependent = is_outbound_employee_scope(scope.display_name, scope.performance_level, scope.position_name or "")
        body = {
            "id": str(scope.id),
            "team_id": str(scope.team_id) if scope.team_id else None,
            "team_key": scope.team_key,
            "display_name": scope.display_name,
            "performance_level": scope.performance_level,
            "position_name": scope.position_name,
            "readiness": readiness,
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
            "period_dependent": period_dependent,
            "admitted_periods": list(admitted_outbound_periods()) if period_dependent else [],
        }
        if not has_period:
            return body
        template = _period_template(scope.display_name, scope.performance_level, scope.position_name or "", year, month)
        period_decision = decision
        period_enabled = period_decision.allows_ratio_edit
        body["global_readiness"] = scope.readiness
        body["global_supported"] = scope.readiness == "supported" and periodless.allows_ratio_edit
        body["period_capability_reason"] = period_decision.reason
        body["period_readiness"] = "supported" if period_enabled else "blocked"
        body["period_supported"] = period_enabled
        body["period_edit_mode"] = "full" if period_enabled else "blocked"
        body["weight_only_allowed"] = False
        if template is not None:
            lines, period = template
            body["lines"] = [dict(line) for line in lines]
            body["period"] = {
                "year": period.get("year"),
                "month": period.get("month"),
                "month_name": period.get("month_name"),
                "period": period.get("period"),
                "status": period.get("status"),
                "approved_binding": period.get("approved_binding"),
                "catalog_template_supported": period.get("catalog_template_supported"),
                "infer_from_august": False,
                "silent_fallback": False,
                "scored_keys": list(period.get("scored_keys") or []),
            }
        else:
            body["lines"] = self.baseline_lines(scope)
            body["period"] = {"year": year, "month": month, "status": None, "catalog_template_supported": False, "infer_from_august": False}
        return body

    def reconcile_period_lines(self, scope: EvaluationScope, year: int, month: int | str, copied_lines: list[dict] | None) -> dict:
        """Choose lines for one destination period.

        Same weighted KPI set: keep copied targets, weights, directions, and
        target modes when each scored line is safe. Weights are not rescaled
        to the source defaults, including a same-month revise whose admin
        already changed them. July copied into August does not share a weighted
        set, so the result is the canonical August template, Productivity
        included, with a diagnostic and ``source_baseline``. Keys outside the
        server template are not kept. An AHT weight above zero is not kept.
        Later months are the technical template, not an August inference.
        """
        copied = [dict(line) for line in (copied_lines or [])]
        canonical = self.baseline_lines(scope, year, month)
        template = _period_template(scope.display_name, scope.performance_level, scope.position_name or "", year, month)
        period = template[1] if template is not None else {}
        blocked = not self.decision_for(scope, year, month).allows_ratio_edit
        diagnostics: list[str] = []
        destination_keys = _weighted_keys(canonical)
        copied_keys = _weighted_keys(copied)
        allowed_keys = {str(line.get("kpi_key") or "") for line in canonical if line.get("kpi_key")}
        if copied_keys != destination_keys or not copied:
            added = sorted(destination_keys - copied_keys)
            removed = sorted(copied_keys - destination_keys)
            if not copied:
                diagnostics.append("No source lines. The draft uses the canonical period template.")
            else:
                diagnostics.append(
                    "Source template changed. Copied lines were replaced with the canonical "
                    f"destination set so weights stay a complete total. Added: {', '.join(added) or 'none'}. "
                    f"Removed: {', '.join(removed) or 'none'}."
                )
            if "Productivity" in destination_keys and "Productivity" not in copied_keys:
                diagnostics.append(
                    "Productivity is on the canonical destination baseline and was not dropped or inferred from another month."
                )
            if period.get("status") == "unconfigured":
                diagnostics.append("This month is unconfigured. August lines and Productivity were not inferred.")
            return {
                "lines": [dict(line) for line in canonical],
                "diagnostics": diagnostics,
                "template_changed": True,
                "preserved_values": False,
                "source_baseline": [dict(line) for line in canonical],
                "blocked": blocked,
                "period_status": period.get("status"),
                "weights_total": float(_weight_total(canonical)),
            }
        by_key = {str(line.get("kpi_key") or ""): line for line in canonical}
        preserved = []
        unsafe = []
        for raw in copied:
            key = str(raw.get("kpi_key") or "")
            if key not in allowed_keys:
                unsafe.append(f"{key or 'blank'} is outside the server template")
                continue
            template_line = by_key[key]
            try:
                weight = float(raw.get("weight"))
            except (TypeError, ValueError):
                unsafe.append(f"{key} weight is not a number")
                continue
            if weight < 0 or weight > 1:
                unsafe.append(f"{key} weight is outside 0 to 1")
                continue
            if key == AHT_KEY and weight > 0:
                unsafe.append("AHT is an optional zero-weight diagnostic and cannot be activated")
                continue
            direction = str(raw.get("direction") or template_line.get("direction") or "")
            if direction not in SUPPORTED_DIRECTIONS:
                unsafe.append(f"{key} direction is not supported")
                continue
            if is_outbound_employee_scope(scope.display_name, scope.performance_level, scope.position_name or "") and key != AHT_KEY and direction != "higher_better":
                unsafe.append(f"{key} direction is not the audited higher-is-better contract")
                continue
            target_mode = str(raw.get("target_mode") or template_line.get("target_mode") or "workbook")
            if target_mode not in {"workbook", "fixed"}:
                unsafe.append(f"{key} target source is not workbook or fixed")
                continue
            target = raw.get("target")
            if target_mode == "fixed":
                try:
                    if target is None or float(target) < 0:
                        unsafe.append(f"{key} fixed target is missing or negative")
                        continue
                    target = float(target)
                except (TypeError, ValueError):
                    unsafe.append(f"{key} fixed target is not a number")
                    continue
            line = _copy_line(template_line)
            line["label"] = raw.get("label") or template_line.get("label") or key
            line["weight"] = weight
            line["direction"] = direction
            line["target_mode"] = target_mode
            line["target"] = target if target_mode == "fixed" else raw.get("target", template_line.get("target"))
            if key == AHT_KEY:
                line["optional"] = True
                line["scored"] = False
                line["enabled"] = False
                line["weight"] = 0.0
            preserved.append(line)
        if unsafe or _weighted_keys(preserved) != destination_keys:
            diagnostics.append(
                "Copied lines were not safe to keep. The canonical destination template was used instead: "
                + "; ".join(unsafe)
            )
            return {
                "lines": [dict(line) for line in canonical],
                "diagnostics": diagnostics,
                "template_changed": False,
                "preserved_values": False,
                "source_baseline": [dict(line) for line in canonical],
                "blocked": blocked,
                "period_status": period.get("status"),
                "weights_total": float(_weight_total(canonical)),
            }
        present = {str(line["kpi_key"]) for line in preserved}
        for line in canonical:
            if str(line.get("kpi_key")) not in present and float(line.get("weight") or 0) == 0:
                preserved.append(dict(line))
                diagnostics.append(f"{line.get('kpi_key')} stays on the template as an optional zero-weight diagnostic.")
        total = _weight_total(preserved)
        if abs(total - Decimal("1")) > Decimal("0.0001"):
            diagnostics.append(
                f"Preserved weights total {float(total):.4f}. They were not rescaled to the source defaults."
            )
        return {
            "lines": preserved,
            "diagnostics": diagnostics,
            "template_changed": False,
            "preserved_values": True,
            "source_baseline": [dict(line) for line in canonical],
            "blocked": blocked,
            "period_status": period.get("status"),
            "weights_total": float(total),
        }
