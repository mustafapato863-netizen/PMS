from __future__ import annotations


def _record_value(record, field: str, default=""):
    if isinstance(record, dict):
        return record.get(field, default)
    return getattr(record, field, default)


_MERGED_TEAM_KEYS = {
    "pre-approvals op final",
    "pre-approvals op dubai",
    "pre-approvals op final shjajm",
    "pre-approvals ip final",
    "pre-approvals ip final dubai",
    "pre-approvals ip final shjajm",
    "pre-approvals",
    "pre-approvals ip elective",
    "pre-approvals ip elective dubai",
}

_PRE_APPROVALS_UAE_KEYS = {
    "pre-approvals",
    "pre-approvals op final",
    "pre-approvals op dubai",
    "pre-approvals op final shjajm",
    "pre-approvals ip final",
    "pre-approvals ip final dubai",
    "pre-approvals ip final shjajm",
    "pre-approvals ip elective",
    "pre-approvals ip elective dubai",
}

_PRE_APPROVALS_OP_FINAL_KEYS = {
    "pre-approvals op final",
    "pre-approvals op dubai",
    "pre-approvals op final shjajm",
}

_PRE_APPROVALS_IP_FINAL_KEYS = {
    "pre-approvals ip final",
    "pre-approvals ip final dubai",
    "pre-approvals ip final shjajm",
}

_PRE_APPROVALS_IP_ELECTIVE_KEYS = {
    "pre-approvals ip elective",
    "pre-approvals ip elective dubai",
}

_CALL_CENTER_KEYS = {"call center", "inbound", "outbound"}

_RCM_KEYS = {
    "rcm",
    "coding",
    "submission",
    "re-submission",
    "pre-approvals",
    "pre-approvals ip offshore",
    "pre-approvals op final",
    "pre-approvals op dubai",
    "pre-approvals op final shjajm",
    "pre-approvals ip final",
    "pre-approvals ip final dubai",
    "pre-approvals ip final shjajm",
    "pre-approvals ip elective",
    "pre-approvals ip elective dubai",
}


def _team_keys(value: str) -> set[str]:
    normalized = str(value).strip().casefold()
    if normalized == "pre-approvals":
        return _PRE_APPROVALS_UAE_KEYS
    if normalized in _PRE_APPROVALS_OP_FINAL_KEYS:
        return _PRE_APPROVALS_OP_FINAL_KEYS
    if normalized in _PRE_APPROVALS_IP_FINAL_KEYS:
        return _PRE_APPROVALS_IP_FINAL_KEYS
    if normalized in _PRE_APPROVALS_IP_ELECTIVE_KEYS:
        return _PRE_APPROVALS_IP_ELECTIVE_KEYS
    if normalized == "call center":
        return _CALL_CENTER_KEYS
    if normalized == "rcm":
        return _RCM_KEYS
    return {normalized}


def user_can_access_team(scope: dict, team_name: str) -> bool:
    if scope.get("legacy_unscoped"):
        return True
    if scope.get("role") == "Admin" or scope.get("is_general_manager"):
        return True
    accessible = set().union(*(_team_keys(str(team)) for team in scope.get("accessible_teams", [])))
    return bool(_team_keys(team_name) & accessible)


def user_can_access_team_level(scope: dict, team_name: str, performance_level: str) -> bool:
    if scope.get("legacy_unscoped"):
        return False
    if scope.get("role") == "Admin" or scope.get("is_general_manager"):
        return True
    if not user_can_access_team(scope, team_name):
        return False
    configured = {
        (team_key, str(level))
        for team, level in scope.get("accessible_team_levels", [])
        for team_key in _team_keys(str(team))
    }
    team_levels = {level for team, level in configured if team == team_name.lower()}
    return not team_levels or performance_level in team_levels


def filter_records_by_scope(records, scope: dict):
    if scope.get("legacy_unscoped"):
        return records
    role = scope.get("role")
    if role in {"Agent", "Executive"}:
        self_id = str(scope.get("employee_id") or scope.get("user_id") or "")
        return [record for record in records if str(_record_value(record, "employee_id")) == self_id]
    if role == "Manager" and not scope.get("is_general_manager"):
        accessible = set().union(*(_team_keys(str(team)) for team in scope.get("accessible_teams", [])))
        return [record for record in records if str(_record_value(record, "team")).lower() in accessible]
    return records


def filter_records_by_team_levels(records, scope: dict):
    """Apply explicit team/level assignments after the broader role scope filter."""
    if scope.get("role") == "Admin" or scope.get("is_general_manager") or scope.get("legacy_unscoped"):
        return records
    configured = {
        (team_key, str(level))
        for team, level in scope.get("accessible_team_levels", [])
        for team_key in _team_keys(str(team))
    }
    if not configured:
        return records
    return [
        record
        for record in records
        if any(
            (team_key, str(_record_value(record, "performance_level"))) in configured
            for team_key in _team_keys(str(_record_value(record, "team")))
        )
    ]
