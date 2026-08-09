from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from statistics import mean
from typing import Any, Iterable

from config.loader import ConfigurationError, find_team_config_by_db_name, load_team_config, resolve_team_config


MONTHS = {name: index for index, name in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1
)}
MONTH_NAMES = {value: key for key, value in MONTHS.items()}
ROUNDING_TOLERANCE = 0.2
DIAGNOSTIC_LABEL = "Operational diagnostic — not included in PMS score"


def number(value: Any) -> float | None:
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _record_value(record: Any, key: str, default: Any = None) -> Any:
    return record.get(key, default) if isinstance(record, dict) else getattr(record, key, default)


def score(record: Any) -> float | None:
    evaluation = _record_value(record, "evaluation")
    value = _record_value(evaluation, "score") if evaluation is not None else None
    return number(value if value is not None else _record_value(record, "score"))


def period_key(record: Any) -> tuple[int, int] | None:
    year = _record_value(record, "year")
    raw_month = _record_value(record, "month", "")
    month = int(raw_month) if str(raw_month).isdigit() and 1 <= int(raw_month) <= 12 else MONTHS.get(str(raw_month))
    return (int(year), month) if year and month else None


def previous_calendar_period(period: tuple[int, int]) -> tuple[int, int]:
    year, month = period
    return (year - 1, 12) if month == 1 else (year, month - 1)


def period_label(period: tuple[int, int] | None) -> str | None:
    return f"{MONTH_NAMES[period[1]]} {period[0]}" if period else None


def _config(record: Any) -> dict[str, Any] | None:
    team = str(_record_value(record, "team", ""))
    try:
        try:
            base = load_team_config(team)
        except ConfigurationError:
            base = find_team_config_by_db_name(team)
            if not base:
                return None
        return resolve_team_config(
            base,
            str(_record_value(record, "performance_level", "Employee") or "Employee"),
            str(_record_value(record, "position", "") or "") or None,
        )
    except ConfigurationError:
        return None


def _normalized_percent(value: float | None) -> float | None:
    if value is None:
        return None
    return value * 100 if abs(value) <= 1 else value


def _employee_key(record: Any) -> str:
    return str(_record_value(record, "employee_id", ""))


def _raw_kpis(record: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in list(_record_value(record, "kpi_values", []) or []):
        item = dict(raw) if isinstance(raw, dict) else {
            key: _record_value(raw, key) for key in (
                "kpi_key", "label", "actual_value", "target_value", "achievement_ratio",
                "weight_applied", "contribution", "direction", "unit", "weight", "target",
            )
        }
        result.append({
            **item,
            "kpi_key": item.get("kpi_key") or item.get("key") or item.get("label"),
            "label": item.get("label") or item.get("kpi_key") or item.get("key"),
            "actual_value": item.get("actual_value", item.get("actual")),
            "target_value": item.get("target_value", item.get("target")),
            "achievement_ratio": item.get("achievement_ratio", item.get("achievement")),
            "weight_applied": item.get("weight_applied", item.get("weight", item.get("weight_pct"))),
            "contribution": item.get("contribution", item.get("weighted_contribution")),
        })
    return result


def _configured_kpis(record: Any) -> tuple[dict[str, dict[str, Any]], str]:
    # Managerial/corporate analysis rows are already materialized from the
    # period-applied database configuration; that persisted metadata is more
    # authoritative than the employee dashboard YAML for the same team name.
    if isinstance(record, dict) and str(_record_value(record, "performance_level", "")).casefold() in {"managerial", "corporate"}:
        applied_config: dict[str, dict[str, Any]] = {}
        for item in _raw_kpis(record):
            key = str(item.get("kpi_key") or "").strip()
            if key:
                applied = {
                    "key": key, "label": item.get("label") or key,
                    "direction": item.get("direction"), "unit": item.get("unit"),
                    "weight": item.get("weight_applied"), "target": item.get("target_value"),
                }
                applied_config[key.casefold()] = applied
                applied_config[str(applied["label"]).casefold()] = applied
        if applied_config:
            return applied_config, "period_applied_record_configuration"
    config = _config(record)
    configured: dict[str, dict[str, Any]] = {}
    for item in (config or {}).get("kpis", []):
        for identity in (item.get("key"), item.get("label")):
            if identity:
                configured[str(identity).casefold()] = item
    if configured:
        return configured, "effective_configuration"
    return {}, "missing_configuration"


def _action_value(action: Any, key: str, default: Any = None) -> Any:
    return _record_value(action, key, default)


def _employee_from_action(action: Any) -> str | None:
    employee = _action_value(action, "employee")
    value = _record_value(employee, "employee_id") if employee is not None else _action_value(action, "employee_id")
    return str(value) if value else None


class ReportingEvidenceService:
    """Canonical reporting semantics over records already authorized by the caller."""

    def effective_grade_status(self, record: Any) -> tuple[str | None, str | None, str]:
        evaluation = _record_value(record, "evaluation")
        persisted_grade = _record_value(evaluation, "grade") if evaluation is not None else _record_value(record, "grade")
        persisted_status = _record_value(record, "status") or (_record_value(evaluation, "status") if evaluation is not None else None)
        if persisted_grade and persisted_status:
            return str(persisted_grade), str(persisted_status), "persisted"
        value = score(record)
        config = _config(record)
        thresholds = (config or {}).get("grade_thresholds", {})
        if value is None or not thresholds:
            return persisted_grade or None, persisted_status or None, "partial_persisted" if persisted_grade or persisted_status else "unavailable"
        ordered = sorted(
            ((str(grade), number(threshold)) for grade, threshold in thresholds.items()),
            key=lambda item: item[1] if item[1] is not None else float("-inf"), reverse=True,
        )
        grade = str(persisted_grade or next((grade for grade, threshold in ordered if threshold is not None and value >= threshold), "E"))
        status = str(persisted_status or ("Below Target" if grade.casefold() in {"d", "e", "poor", "unsatisfactory"} else "On Track"))
        return grade, status, "persisted_with_effective_fallback" if persisted_grade or persisted_status else "effective_period_configuration"

    def is_below_target(self, record: Any) -> bool:
        grade, status, _ = self.effective_grade_status(record)
        normalized_status, normalized_grade = str(status or "").casefold(), str(grade or "").casefold()
        return "below" in normalized_status or "risk" in normalized_status or normalized_grade in {"d", "e", "poor", "unsatisfactory"}

    def _normalized_record_kpis(self, record: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        configured, source = _configured_kpis(record)
        rows: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        seen: Counter[str] = Counter()
        employee_id = _employee_key(record)
        for raw in _raw_kpis(record):
            key = str(raw.get("kpi_key") or "").strip()
            if not key:
                continue
            seen[key.casefold()] += 1
            configured_item = configured.get(key.casefold()) or configured.get(str(raw.get("label") or "").casefold())
            if configured_item is None:
                issues.append({"code": "persisted_kpi_missing_configuration", "severity": "high", "kpi": key, "employee_id": employee_id, "blocks_ranking": True})
                continue
            persisted_weight = _normalized_percent(number(raw.get("weight_applied")))
            configured_weight = _normalized_percent(number(configured_item.get("weight")))
            weight = persisted_weight if persisted_weight is not None else configured_weight
            direction = str(configured_item.get("direction") or raw.get("direction") or "").strip()
            unit = str(configured_item.get("unit") or raw.get("unit") or "").strip()
            target = number(raw.get("target_value"))
            actual = number(raw.get("actual_value"))
            contribution = _normalized_percent(number(raw.get("contribution")))
            if contribution is not None:
                contribution = min(max(contribution, 0.0), max(weight or 0.0, 0.0))
            diagnostic = (weight or 0) == 0
            invalid_target = target is None or target == 0
            valid_direction = direction in {"higher_better", "lower_better"}
            included = bool((weight or 0) > 0 and not invalid_target and valid_direction)
            achievement = None
            if included and actual is not None:
                achievement = actual / target if direction == "higher_better" else (target / actual if actual != 0 else 1.0)
                achievement = round(min(max(achievement, 0.0), 1.0) * 100, 2)
            lost = round(max(0.0, float(weight) - contribution), 2) if included and contribution is not None else None
            target_gap = None
            if included and actual is not None:
                target_gap = round(max(0.0, target - actual) if direction == "higher_better" else max(0.0, actual - target), 2)
            warning_state = None
            if diagnostic:
                warning_state = "diagnostic_not_scored"
            elif invalid_target:
                warning_state = "invalid_target"
            elif not valid_direction:
                warning_state = "invalid_direction"
            rows.append({
                "key": key, "name": configured_item.get("label") or raw.get("label") or key,
                "team": _record_value(record, "team"), "position": _record_value(record, "position"),
                "employee_id": employee_id, "employee": _record_value(record, "employee_name"),
                "actual": actual, "target": None if invalid_target else target, "configured_target": target,
                "unit": unit or None, "direction": direction or None, "achievement": achievement,
                "weight": 0.0 if diagnostic else weight, "weighted_contribution": contribution if included else None,
                "maximum_contribution": weight if included else None, "lost_points": lost, "target_gap": target_gap,
                "included_in_score": included, "diagnostic_status": DIAGNOSTIC_LABEL if diagnostic else None,
                "diagnostic_label": DIAGNOSTIC_LABEL if diagnostic else None,
                "configuration_state": source if included or diagnostic else "requires_review",
                "warning_state": warning_state, "state": "ready" if included or diagnostic else "configuration_requires_review",
                "status": "invalid target" if invalid_target else "below target" if achievement is not None and achievement < 100 else "on target",
            })
            if invalid_target:
                issues.append({"code": "zero_target" if target == 0 else "missing_target", "severity": "high", "kpi": key, "employee_id": employee_id, "blocks_ranking": True})
            if diagnostic:
                issues.append({"code": "diagnostic_metric", "severity": "info", "kpi": key, "employee_id": employee_id, "blocks_ranking": True})
            if not valid_direction:
                issues.append({"code": "invalid_direction", "severity": "high", "kpi": key, "employee_id": employee_id, "blocks_ranking": True})
            if not unit:
                issues.append({"code": "missing_unit", "severity": "medium", "kpi": key, "employee_id": employee_id, "blocks_ranking": False})
            if persisted_weight is not None and configured_weight is not None and abs(persisted_weight - configured_weight) > 0.01:
                issues.append({"code": "weight_mismatch", "severity": "high", "kpi": key, "employee_id": employee_id, "blocks_ranking": False, "expected": configured_weight, "actual": persisted_weight})
        for key, count in seen.items():
            if count > 1:
                issues.append({"code": "duplicate_kpi", "severity": "high", "kpi": key, "employee_id": employee_id, "blocks_ranking": True})
        raw_identities = {str(item.get("kpi_key") or "").casefold() for item in _raw_kpis(record)}
        configured_unique = {str(item.get("key") or item.get("label") or "").casefold(): item for item in configured.values()}
        for identity, item in configured_unique.items():
            if identity and identity not in raw_identities and str(item.get("label") or "").casefold() not in raw_identities:
                issues.append({"code": "configured_kpi_missing_evidence", "severity": "medium", "kpi": item.get("label") or item.get("key"), "employee_id": employee_id, "blocks_ranking": False})
        return rows, issues

    def kpi_evidence(self, current: list[Any], previous: list[Any]) -> tuple[list[dict[str, Any]], list[str]]:
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        prior: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        warnings: list[str] = []
        for records, target in ((current, grouped), (previous, prior)):
            for record in records:
                rows, issues = self._normalized_record_kpis(record)
                for issue in issues:
                    if issue["code"] == "persisted_kpi_missing_configuration":
                        warnings.append(f"Applied-configuration mismatch: persisted KPI '{issue['kpi']}' is not in the effective configuration and was excluded from scored output.")
                    elif issue["code"] in {"zero_target", "missing_target"}:
                        warnings.append(f"{issue['kpi']} has a missing or zero target; its configuration requires review.")
                for item in rows:
                    target[(str(item["team"] or ""), str(item["position"] or ""), item["key"].casefold())].append(item)
        result: list[dict[str, Any]] = []
        for identity, values in grouped.items():
            first = values[0]
            prior_values = prior.get(identity, [])
            def avg(field: str, rows: list[dict[str, Any]]) -> float | None:
                valid = [number(row.get(field)) for row in rows]
                valid = [value for value in valid if value is not None]
                return round(mean(valid), 2) if valid else None
            actual, previous_actual = avg("actual", values), avg("actual", prior_values)
            direction = first["direction"]
            change = round(actual - previous_actual, 2) if actual is not None and previous_actual is not None else None
            relative = round(change / abs(previous_actual) * 100, 2) if change is not None and previous_actual not in {None, 0} else None
            score_movement = None
            current_contribution, prior_contribution = avg("weighted_contribution", values), avg("weighted_contribution", prior_values)
            if current_contribution is not None and prior_contribution is not None:
                score_movement = round(current_contribution - prior_contribution, 2)
            result.append({
                **{key: first.get(key) for key in ("key", "name", "team", "position", "target", "configured_target", "unit", "direction", "weight", "included_in_score", "diagnostic_status", "diagnostic_label", "configuration_state", "warning_state", "state", "status")},
                "actual": actual, "value": actual, "display_value": actual, "previous": previous_actual,
                "achievement": avg("achievement", values), "weighted_contribution": current_contribution,
                "maximum_contribution": avg("maximum_contribution", values), "lost_points": avg("lost_points", values),
                "target_gap": avg("target_gap", values), "score_point_movement": score_movement,
                "absolute_value_change": change, "percentage_point_change": change if first.get("unit") == "%" else None,
                "relative_percentage_change": relative,
                "movement": "positive" if change is not None and ((direction == "higher_better" and change >= 0) or (direction == "lower_better" and change <= 0)) else "negative" if change is not None else "unavailable",
                "warnings": [first["warning_state"]] if first.get("warning_state") else [],
            })
        result.sort(key=lambda item: (not item["included_in_score"], item["lost_points"] is None, -(item["lost_points"] or 0), item["name"]))
        return result, list(dict.fromkeys(warnings))

    def summary(self, current: list[Any], previous: list[Any], actions: list[Any] | None = None) -> dict[str, Any]:
        current_scores = [value for row in current if (value := score(row)) is not None]
        previous_scores = [value for row in previous if (value := score(row)) is not None]
        current_average = round(mean(current_scores), 2) if current_scores else None
        previous_average = round(mean(previous_scores), 2) if previous_scores else None
        change = round(current_average - previous_average, 2) if current_average is not None and previous_average is not None else None
        below = {_employee_key(row) for row in current if self.is_below_target(row)}
        critical = [item for item in (actions or []) if str(_action_value(item, "status", "")).casefold() not in {"completed", "cancelled"} and str(_action_value(item, "priority", "")).casefold() == "high"]
        return {"state": "ready" if current_scores else "unavailable", "average_score": current_average, "previous_score": previous_average,
                "score_point_change": change, "score_change": change, "relative_percentage_change": round(change / abs(previous_average) * 100, 2) if change is not None and previous_average not in {None, 0} else None,
                "total_employees": len({_employee_key(row) for row in current}), "employees_below_target": len(below), "critical_risks": len(critical), "record_count": len(current)}

    def rankings(self, current: list[Any], limit: int = 10) -> dict[str, list[dict[str, Any]]]:
        by_employee: dict[str, list[Any]] = defaultdict(list)
        for record in current:
            if score(record) is not None:
                by_employee[_employee_key(record)].append(record)
        rows = []
        for employee_id, records in by_employee.items():
            values = [score(record) for record in records if score(record) is not None]
            first = records[0]
            grade, status, source = self.effective_grade_status(first)
            rows.append({"employee": _record_value(first, "employee_name"), "employee_id": employee_id, "employee_name": _record_value(first, "employee_name"), "team": _record_value(first, "team"), "position": _record_value(first, "position"),
                         "score": round(mean(values), 2), "current_score": round(mean(values), 2), "grade": grade, "status": status, "classification_source": source, "is_below": any(self.is_below_target(record) for record in records)})
        rows.sort(key=lambda row: (-row["score"], row["employee_name"] or row["employee_id"]))
        top = rows[:limit]; top_ids = {row["employee_id"] for row in top}
        bottom = [row for row in reversed(rows) if row["employee_id"] not in top_ids][:limit]
        return {"top": top, "bottom": bottom, "all": rows}

    def trend(self, records: list[Any], primary: tuple[int, int], requested_count: int = 6) -> dict[str, Any]:
        periods = sorted({period_key(row) for row in records if period_key(row) and period_key(row) <= primary})[-requested_count:]
        series = []
        for period in periods:
            values = [score(row) for row in records if period_key(row) == period and score(row) is not None]
            if values:
                series.append({"label": period_label(period), "value": round(mean(values), 2)})
        count = len(series)
        if count == 0: title, state = "Trend Unavailable", "unavailable"
        elif count == 1: title, state = f"{series[0]['label']} Only", "single_period"
        elif count < requested_count: title, state = f"Score Trend — {count} Available Periods", "partial"
        else: title, state = f"Score Trend — Last {requested_count} Months", "ready"
        return {"series": series, "available_periods": [item["label"] for item in series], "period_count": count, "requested_range": requested_count,
                "actual_range": {"from": series[0]["label"], "to": series[-1]["label"]} if series else None, "trend_state": state, "title": title}

    def _config_signature(self, record: Any) -> tuple[Any, ...]:
        rows, _ = self._normalized_record_kpis(record)
        return tuple(sorted((row["key"].casefold(), row["weight"], row["target"], row["direction"], row["unit"]) for row in rows))

    def movement(self, current: list[Any], previous: list[Any], primary: tuple[int, int] | None = None) -> dict[str, Any]:
        summary = self.summary(current, previous)
        current_by_id = {_employee_key(row): row for row in current if score(row) is not None}
        previous_by_id = {_employee_key(row): row for row in previous if score(row) is not None}
        matched = sorted(current_by_id.keys() & previous_by_id.keys()); current_only = sorted(current_by_id.keys() - previous_by_id.keys()); previous_only = sorted(previous_by_id.keys() - current_by_id.keys())
        reported = summary["score_point_change"]
        base = {"comparison_state": "available" if reported is not None else "unavailable", "comparison_period": period_label(previous_calendar_period(primary)) if primary else None,
                "current_period": period_label(primary), "previous_overall_score": summary["previous_score"], "current_overall_score": summary["average_score"], "total_score_point_change": reported,
                "matched_employee_count": len(matched), "joiner_count": len(current_only), "leaver_count": len(previous_only), "current_only_employee_count": len(current_only), "previous_only_employee_count": len(previous_only)}
        if reported is None:
            return {**base, "kpi_contribution_movements": [], "team_contribution_movements": [], "joiner_effect": None, "leaver_effect": None, "population_scope_mix_effect": None,
                    "configuration_mismatch_effect": None, "configuration_version_effect": None, "missing_evidence_effect": None, "missing_incomparable_data_effect": None, "residual": None,
                    "reconciliation_state": "unavailable", "rounding_tolerance": ROUNDING_TOLERANCE, "narrative": "Previous-calendar-month comparison is unavailable.", "warnings": ["An adjacent-month movement bridge cannot be produced."]}
        current_matched = mean(score(current_by_id[key]) for key in matched) if matched else None
        previous_matched = mean(score(previous_by_id[key]) for key in matched) if matched else None
        joiner = round(summary["average_score"] - current_matched, 4) if current_matched is not None else round(reported, 4)
        leaver = round(previous_matched - summary["previous_score"], 4) if previous_matched is not None else 0.0
        kpi_movements: dict[str, float] = defaultdict(float); team_movements: dict[str, float] = defaultdict(float)
        config_effect = missing_effect = scope_mix = 0.0
        for key in matched:
            current_row, previous_row = current_by_id[key], previous_by_id[key]
            employee_delta = score(current_row) - score(previous_row)
            team = str(_record_value(current_row, "team") or "Unspecified")
            team_movements[team] += employee_delta / len(matched)
            if (_record_value(current_row, "team"), _record_value(current_row, "position"), _record_value(current_row, "performance_level")) != (_record_value(previous_row, "team"), _record_value(previous_row, "position"), _record_value(previous_row, "performance_level")):
                scope_mix += employee_delta / len(matched); continue
            if self._config_signature(current_row) != self._config_signature(previous_row):
                config_effect += employee_delta / len(matched); continue
            current_kpis, _ = self._normalized_record_kpis(current_row); previous_kpis, _ = self._normalized_record_kpis(previous_row)
            current_contrib = {row["key"]: row["weighted_contribution"] for row in current_kpis if row["weighted_contribution"] is not None}
            previous_contrib = {row["key"]: row["weighted_contribution"] for row in previous_kpis if row["weighted_contribution"] is not None}
            common = current_contrib.keys() & previous_contrib.keys()
            if not common:
                missing_effect += employee_delta / len(matched); continue
            for kpi_key in common:
                kpi_movements[kpi_key] += (current_contrib[kpi_key] - previous_contrib[kpi_key]) / len(matched)
        movement_rows = [{"key": key, "label": key, "score_point_change": round(value, 4)} for key, value in sorted(kpi_movements.items(), key=lambda item: abs(item[1]), reverse=True)]
        team_rows = [{"team": key, "score_point_change": round(value, 4)} for key, value in sorted(team_movements.items(), key=lambda item: abs(item[1]), reverse=True)]
        explained = joiner + leaver + scope_mix + config_effect + missing_effect + sum(item["score_point_change"] for item in movement_rows)
        residual = round(reported - explained, 4)
        partial = bool(config_effect or missing_effect or abs(residual) > ROUNDING_TOLERANCE)
        strongest_negative = next((row for row in movement_rows if row["score_point_change"] < 0), None)
        strongest_positive = next((row for row in movement_rows if row["score_point_change"] > 0), None)
        verb = "increased" if reported > 0 else "declined" if reported < 0 else "was unchanged"
        narrative = f"Overall PMS Score {verb} from {summary['previous_score']:.1f}% to {summary['average_score']:.1f}%, a movement of {abs(reported):.1f} score points."
        if strongest_negative: narrative += f" {strongest_negative['label']} contributed to the decline."
        if strongest_positive: narrative += f" {strongest_positive['label']} partially offset negative movement."
        if abs(residual) > ROUNDING_TOLERANCE: narrative += f" A residual of {residual:+.1f} points remains attributable to population, configuration, or incomparable evidence."
        warnings = []
        if config_effect: warnings.append("Compared records used different applied KPI configurations.")
        if missing_effect: warnings.append("Some matched records lacked comparable KPI contribution evidence.")
        return {**base, "kpi_contribution_movements": movement_rows, "team_contribution_movements": team_rows,
                "joiner_effect": round(joiner, 2), "leaver_effect": round(leaver, 2), "population_scope_mix_effect": round(scope_mix, 2),
                "configuration_mismatch_effect": round(config_effect, 2), "configuration_version_effect": round(config_effect, 2),
                "missing_evidence_effect": round(missing_effect, 2), "missing_incomparable_data_effect": round(missing_effect, 2), "residual": round(residual, 2),
                "reconciliation_state": "partial" if partial else "reconciled", "rounding_tolerance": ROUNDING_TOLERANCE, "narrative": narrative, "warnings": warnings}

    def lowest_kpis(self, current: list[Any], previous: list[Any]) -> dict[str, Any]:
        rows, _ = self.kpi_evidence(current, previous)
        ranked = [row for row in rows if row["included_in_score"] and row["lost_points"] is not None]
        ranked.sort(key=lambda row: (-(row["lost_points"] or 0), row["achievement"] if row["achievement"] is not None else float("inf"), -(row["target_gap"] or 0), row["score_point_movement"] if row["score_point_movement"] is not None else 0, -(row["weight"] or 0), row["name"]))
        output = []
        for rank, row in enumerate(ranked, 1):
            output.append({"rank": rank, **row})
        excluded = [row for row in rows if not row["included_in_score"]]
        return {"rows": output, "configuration_issues_excluded": excluded, "ranking_method": "weighted_lost_points, achievement, target_gap, deterioration, weight"}

    def lowest_employees(self, current: list[Any], previous: list[Any], records: list[Any], actions: list[Any] | None, action_evidence_authorized: bool) -> dict[str, Any]:
        previous_by_id = {_employee_key(row): row for row in previous if score(row) is not None}
        action_map: dict[str, list[Any]] = defaultdict(list)
        for action in actions or []:
            if employee_id := _employee_from_action(action): action_map[employee_id].append(action)
        repeated_ids = {row["employee_id"] for row in self.three_month_low(records, period_key(current[0]) if current else (0, 1), actions, action_evidence_authorized)["rows"]}
        rows = []
        for record in current:
            current_score = score(record)
            if current_score is None: continue
            employee_id = _employee_key(record); prior = score(previous_by_id[employee_id]) if employee_id in previous_by_id else None
            kpis, _ = self._normalized_record_kpis(record); scored = [row for row in kpis if row["included_in_score"]]
            weakest = max(scored, key=lambda row: (row["lost_points"] or 0, -(row["achievement"] or 999)), default=None)
            linked = action_map.get(employee_id, []); root_state = self._root_state(record, linked)
            grade, status, _ = self.effective_grade_status(record)
            rows.append({"employee": _record_value(record, "employee_name"), "employee_id": employee_id, "team": _record_value(record, "team"), "position": _record_value(record, "position"),
                         "current_score": current_score, "previous_score": prior, "score_point_change": round(current_score-prior, 2) if prior is not None else None,
                         "grade": grade, "status": status, "weakest_scored_kpi": weakest["name"] if weakest else None,
                         "weighted_lost_points": round(sum(row["lost_points"] or 0 for row in scored), 2), "root_cause_state": root_state,
                         "existing_action_status": str(_action_value(linked[0], "status")) if linked else ("Unavailable by permission" if not action_evidence_authorized else "No action"),
                         "feedback_evidence_state": self._feedback_state(linked) if action_evidence_authorized else "Unavailable by permission",
                         "three_month_risk": employee_id in repeated_ids, "source_dashboard_reference": f"/employee/{employee_id}?month={_record_value(record, 'month')}&year={_record_value(record, 'year')}"})
        rows.sort(key=lambda row: (row["current_score"], -(row["weighted_lost_points"] or 0), row["employee"] or row["employee_id"]))
        for index, row in enumerate(rows, 1): row["rank"] = index
        return {"rows": rows}

    @staticmethod
    def _feedback_state(actions: list[Any]) -> str:
        feedback = [action for action in actions if any(token in str(_action_value(action, "action_type", "")).casefold() for token in ("feedback", "coaching", "pip", "training", "review"))]
        if not feedback: return "Not recorded"
        return str(_action_value(feedback[0], "status", "Recorded"))

    @staticmethod
    def _root_state(record: Any, actions: list[Any]) -> str:
        for action in actions:
            if _action_value(action, "root_cause_note") and _action_value(action, "evidence_reference"): return "Confirmed"
            if _action_value(action, "root_cause_note"): return "Likely"
        evaluation = _record_value(record, "evaluation")
        if _record_value(evaluation, "root_cause"): return "Likely"
        return "Unclassified / Requires Review"

    def three_month_low(self, records: list[Any], primary: tuple[int, int], actions: list[Any] | None, action_evidence_authorized: bool) -> dict[str, Any]:
        p2 = previous_calendar_period(primary); p1 = previous_calendar_period(p2); required = [p1, p2, primary]
        by_employee: dict[str, dict[tuple[int, int], Any]] = defaultdict(dict)
        for record in records:
            if period_key(record) in required and score(record) is not None: by_employee[_employee_key(record)][period_key(record)] = record
        action_map: dict[str, list[Any]] = defaultdict(list)
        for action in actions or []:
            if employee_id := _employee_from_action(action): action_map[employee_id].append(action)
        rows, insufficient = [], []
        for employee_id, history in by_employee.items():
            missing = [period_label(period) for period in required if period not in history]
            if missing:
                first = next(iter(history.values()))
                insufficient.append({"employee": _record_value(first, "employee_name"), "employee_id": employee_id, "missing_periods": missing}); continue
            sequence = [history[period] for period in required]
            if not all(self.is_below_target(record) for record in sequence): continue
            signatures = [self._config_signature(record) for record in sequence]
            continuity = "compatible" if signatures[0] == signatures[1] == signatures[2] else "changed_configuration_disclosed"
            per_month_kpis = [self._normalized_record_kpis(record)[0] for record in sequence]
            failures = Counter(row["key"] for month in per_month_kpis for row in month if row["included_in_score"] and (row["achievement"] or 100) < 100)
            repeated = failures.most_common(1)[0] if failures else (None, 0)
            scores = [score(record) for record in sequence]; linked = action_map.get(employee_id, [])
            last = sequence[-1]
            rows.append({"employee": _record_value(last, "employee_name"), "employee_id": employee_id, "team": _record_value(last, "team"), "position": _record_value(last, "position"),
                         "months": [{"period": period_label(period), "score": scores[index], "grade": self.effective_grade_status(sequence[index])[0], "status": self.effective_grade_status(sequence[index])[1]} for index, period in enumerate(required)],
                         "three_month_average": round(mean(scores), 2), "trend": round(scores[-1]-scores[0], 2), "repeated_weakest_kpi": repeated[0], "repeated_kpi_failures": repeated[1],
                         "repeated_weighted_lost_points": round(sum(row["lost_points"] or 0 for month in per_month_kpis for row in month if row["key"] == repeated[0]), 2),
                         "current_action_status": str(_action_value(linked[0], "status")) if linked else ("Unavailable by permission" if not action_evidence_authorized else "No action"),
                         "root_cause_evidence_state": self._root_state(last, linked), "feedback_evidence_state": self._feedback_state(linked) if action_evidence_authorized else "Unavailable by permission",
                         "recommended_escalation_category": "Management review" if not linked else "Monitor existing intervention", "configuration_continuity_state": continuity,
                         "warnings": ["Applied KPI configuration changed within the three-month sequence."] if continuity != "compatible" else []})
        rows.sort(key=lambda row: (row["three_month_average"], row["trend"], -row["repeated_weighted_lost_points"], row["employee"] or row["employee_id"]))
        return {"rows": rows, "insufficient_history": insufficient, "required_periods": [period_label(period) for period in required]}

    def configuration_audit(self, records: list[Any], primary: tuple[int, int]) -> dict[str, Any]:
        comparison = previous_calendar_period(primary); issues: list[dict[str, Any]] = []
        labels = {"persisted_kpi_missing_configuration": ("Persisted KPI missing from effective configuration", "Remove stale evidence or correct the applied configuration."),
                  "configured_kpi_missing_evidence": ("Configured KPI missing from performance evidence", "Verify source upload and KPI mapping."), "weight_mismatch": ("Weight mismatch", "Align persisted and effective KPI weights."),
                  "duplicate_kpi": ("Duplicate KPI", "Remove the duplicate KPI evidence row."), "zero_target": ("Zero target", "Configure a non-zero target or an explicit zero-target rule."),
                  "missing_target": ("Missing target", "Configure the KPI target."), "invalid_direction": ("Invalid direction", "Use higher_better or lower_better."),
                  "missing_unit": ("Missing unit", "Configure the KPI display unit."), "diagnostic_metric": ("Non-scored diagnostic metric", "No correction required; keep it excluded from PMS score.")}
        scoped = [record for record in records if period_key(record) in {primary, comparison}]
        for record in scoped:
            _, raw_issues = self._normalized_record_kpis(record)
            for issue in raw_issues:
                title, correction = labels[issue["code"]]
                issues.append({"severity": issue["severity"], "issue": title, "code": issue["code"], "scope": f"{_record_value(record, 'team')} · {_record_value(record, 'position') or _record_value(record, 'performance_level')}",
                               "employee": _record_value(record, "employee_name"), "employee_id": _employee_key(record), "kpi": issue.get("kpi"), "current_period": period_label(primary), "comparison_period": period_label(comparison),
                               "expected_state": issue.get("expected") or "Valid period-applied KPI configuration and evidence", "actual_state": issue.get("actual") or title,
                               "effect_on_analysis": "Excluded from ranking/reconciliation" if issue.get("blocks_ranking") else "Analysis warning; value is not silently repaired",
                               "recommended_correction": correction, "blocks_ranking_or_reconciliation": bool(issue.get("blocks_ranking"))})
            grade, status, source = self.effective_grade_status(record)
            if source in {"unavailable", "partial_persisted"}:
                issues.append({"severity": "medium", "issue": "Stored grade/status missing", "code": "missing_grade_status", "scope": str(_record_value(record, "team")), "employee": _record_value(record, "employee_name"), "employee_id": _employee_key(record), "kpi": None,
                               "current_period": period_label(primary), "comparison_period": period_label(comparison), "expected_state": "Persisted grade and status", "actual_state": f"grade={grade}, status={status}",
                               "effect_on_analysis": "Classification may be unavailable", "recommended_correction": "Persist the canonical grade and status for the period.", "blocks_ranking_or_reconciliation": False})
            if isinstance(record, dict) and not _record_value(record, "configuration_version"):
                issues.append({"severity": "medium", "issue": "Missing configuration version", "code": "missing_configuration_version", "scope": str(_record_value(record, "team")), "employee": _record_value(record, "employee_name"), "employee_id": _employee_key(record), "kpi": None,
                               "current_period": period_label(primary), "comparison_period": period_label(comparison), "expected_state": "Traceable applied configuration version", "actual_state": "No version identifier in reporting evidence",
                               "effect_on_analysis": "Continuity is inferred from KPI signatures", "recommended_correction": "Expose the applied configuration version in the canonical record contract.", "blocks_ranking_or_reconciliation": False})
        by_employee: dict[str, dict[tuple[int, int], Any]] = defaultdict(dict)
        for record in scoped: by_employee[_employee_key(record)][period_key(record)] = record
        for employee_id, history in by_employee.items():
            if primary in history and comparison in history and self._config_signature(history[primary]) != self._config_signature(history[comparison]):
                record = history[primary]
                issues.append({"severity": "high", "issue": "Different configurations across compared periods", "code": "configuration_changed", "scope": str(_record_value(record, "team")), "employee": _record_value(record, "employee_name"), "employee_id": employee_id, "kpi": None,
                               "current_period": period_label(primary), "comparison_period": period_label(comparison), "expected_state": "Comparable applied KPI signature", "actual_state": "KPI signature changed",
                               "effect_on_analysis": "Movement is separated as a configuration effect", "recommended_correction": "Review version compatibility before causal interpretation.", "blocks_ranking_or_reconciliation": True})
        counts = Counter(issue["severity"] for issue in issues)
        return {"rows": issues, "summary": dict(counts), "diagnostic_only": True}

    @staticmethod
    def _cause_category(text: str) -> str:
        value = text.casefold(); process = any(token in value for token in ("process", "system", "workflow", "sla", "capacity", "tool", "quality")); staff = any(token in value for token in ("attendance", "coaching", "training", "behavior", "employee", "productivity", "skill"))
        return "Both" if process and staff else "Process" if process else "Staff" if staff else "Requires Review"

    def root_cause_matrix(self, current: list[Any], actions: list[Any] | None, audit: dict[str, Any], action_evidence_authorized: bool) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for action in actions or []:
            note = str(_action_value(action, "root_cause_note", "") or "").strip()
            if not note: continue
            evidence = _action_value(action, "evidence_reference"); confidence = "Confirmed" if evidence else "Likely"; employee_id = _employee_from_action(action)
            employee = _action_value(action, "employee")
            created = _action_value(action, "created_at")
            rows.append({"cause_title": note, "classification": self._cause_category(note), "confidence": confidence, "scope": str(_record_value(_action_value(action, "team"), "name", _action_value(action, "team", ""))),
                         "linked_kpi": _action_value(action, "linked_kpi_key"), "linked_employees": [_record_value(employee, "employee_name") or employee_id] if employee_id else [],
                         "evidence_source_type": "Corrective action evidence" if evidence else "Corrective action note", "evidence_reference": evidence,
                         "evidence_date": created.isoformat() if hasattr(created, "isoformat") else created, "confirmed_by": _record_value(_action_value(action, "created_by"), "username") if evidence else None,
                         "confirmation_date": created.isoformat() if evidence and hasattr(created, "isoformat") else created if evidence else None, "impact_type": "Linked action records", "quantitative_impact": None,
                         "evidence_mentions": 1, "linked_action_records": 1, "action_linkage": str(_action_value(action, "id", "")), "warning": None if evidence else "Rule-derived from an action note; not confirmed."})
        for issue in audit["rows"]:
            if issue["severity"] == "info": continue
            rows.append({"cause_title": issue["issue"], "classification": "Data / Configuration", "confidence": "Data / Configuration Issue", "scope": issue["scope"], "linked_kpi": issue["kpi"], "linked_employees": [issue["employee"]] if issue["employee"] else [],
                         "evidence_source_type": "Applied configuration audit", "evidence_reference": issue["code"], "evidence_date": issue["current_period"], "confirmed_by": None, "confirmation_date": None,
                         "impact_type": "Analysis limitation", "quantitative_impact": None, "evidence_mentions": 1, "linked_action_records": 0, "action_linkage": None, "warning": issue["effect_on_analysis"]})
        evidenced_employees = {value for row in rows for value in row["linked_employees"]}
        for record in current:
            if self.is_below_target(record) and _record_value(record, "employee_name") not in evidenced_employees:
                evaluation = _record_value(record, "evaluation"); root = _record_value(evaluation, "root_cause")
                title = _record_value(root, "kpi") or "Underperformance requires management review"
                rows.append({"cause_title": str(title), "classification": "Requires Review", "confidence": "Likely" if root else "Unclassified / Requires Review", "scope": str(_record_value(record, "team")), "linked_kpi": _record_value(root, "kpi"), "linked_employees": [_record_value(record, "employee_name")],
                             "evidence_source_type": "Performance evaluation pattern" if root else "Current-period classification", "evidence_reference": str(_record_value(record, "id", "")), "evidence_date": period_label(period_key(record)), "confirmed_by": None, "confirmation_date": None,
                             "impact_type": "Requires review", "quantitative_impact": None, "evidence_mentions": 1, "linked_action_records": 0, "action_linkage": None, "warning": "No persisted confirmation evidence is available."})
        if not action_evidence_authorized:
            rows.insert(0, {"cause_title": "Corrective-action evidence unavailable by permission", "classification": "Requires Review", "confidence": "Unclassified / Requires Review", "scope": "Authorized report scope", "linked_kpi": None, "linked_employees": [], "evidence_source_type": "Authorization boundary", "evidence_reference": None, "evidence_date": None, "confirmed_by": None, "confirmation_date": None, "impact_type": "Evidence unavailable", "quantitative_impact": None, "evidence_mentions": 0, "linked_action_records": 0, "action_linkage": None, "warning": "The report does not expose action data without view_actions permission."})
        groups = {category: [row for row in rows if row["classification"] == category] for category in ("Process", "Staff", "Both", "Data / Configuration", "Requires Review")}
        return {"rows": rows, "groups": groups, "impact_label": "Evidence mentions / linked action records"}

    def build(self, records: list[Any], primary: tuple[int, int], actions: list[Any] | None = None, *, action_evidence_authorized: bool = False) -> dict[str, Any]:
        comparison = previous_calendar_period(primary); current = [row for row in records if period_key(row) == primary]; previous = [row for row in records if period_key(row) == comparison]
        kpis, warnings = self.kpi_evidence(current, previous); movement = self.movement(current, previous, primary)
        audit = self.configuration_audit(records, primary); repeated = self.three_month_low(records, primary, actions, action_evidence_authorized)
        lowest_employees = self.lowest_employees(current, previous, records, actions, action_evidence_authorized) if current else {"rows": []}
        return {"primary_period": primary, "comparison_period": comparison, "comparison_state": "available" if previous else "unavailable", "current": current, "previous": previous,
                "summary": self.summary(current, previous, actions if action_evidence_authorized else None), "kpis": kpis, "rankings": self.rankings(current), "trend": self.trend(records, primary), "movement": movement,
                "overall_score_movement_bridge": movement, "lowest_kpis_weighted_impact": self.lowest_kpis(current, previous), "lowest_employees_current_period": lowest_employees,
                "three_month_consecutive_low_performers": repeated, "applied_configuration_audit": audit,
                "root_cause_evidence_matrix": self.root_cause_matrix(current, actions, audit, action_evidence_authorized),
                "grade_distribution": dict(Counter((self.effective_grade_status(row)[0] or "Unavailable") for row in current)),
                "warnings": list(dict.fromkeys(warnings + movement.get("warnings", []) + ([] if previous else [f"Comparison unavailable: {period_label(comparison)} has no valid comparable data."])))}
