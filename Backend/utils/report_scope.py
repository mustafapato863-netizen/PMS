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


FUNCTION_VIEWER_FUNCTIONS = ("Call Center", "RCM", "Pre-Approvals", "Marketing")


# "Functions" are the parent domains that ``_team_keys`` already expands into
# their source teams (the same values the Insights ``team`` filter accepts as
# rollups). A team that is not part of any parent domain (Marketing, Sales,
# CSR, Pharmacy, Inbound UAE, ...) is its own function, mirroring the
# ``_team_keys`` fallback of an exact team match. Order is broadest first:
# UAE Pre-Approvals teams belong to RCM *and* to the narrower Pre-Approvals
# function, exactly as ``_RCM_KEYS`` and ``_PRE_APPROVALS_UAE_KEYS`` overlap.
_FUNCTION_TEAM_KEYS: dict[str, set[str]] = {
    "Call Center": _CALL_CENTER_KEYS,
    "RCM": _RCM_KEYS,
    "Pre-Approvals": _PRE_APPROVALS_UAE_KEYS,
}


def functions_for_team(team_name: str) -> list[str]:
    """Return every function (parent domain) the given team rolls up into."""
    normalized = str(team_name or "").strip()
    if not normalized:
        return []
    key = normalized.casefold()
    parents = [function for function, keys in _FUNCTION_TEAM_KEYS.items() if key in keys]
    return parents or [normalized]


def function_for_team(team_name: str) -> str | None:
    """Map a team to its primary (broadest) function.

    ``Inbound`` -> ``Call Center``, ``Coding`` -> ``RCM``,
    ``Pre-Approvals OP Dubai`` -> ``RCM`` (also listed under ``Pre-Approvals``
    by :func:`functions_for_team`), ``Marketing`` -> ``Marketing``.
    """
    functions = functions_for_team(team_name)
    return functions[0] if functions else None


def function_team_keys(function_name: str) -> set[str]:
    """Casefolded source-team keys covered by a function selection."""
    return _team_keys(str(function_name))


def user_can_access_team(scope: dict, team_name: str) -> bool:
    if scope.get("role") == "Function Viewer":
        allowed_functions = {
            str(name).strip().casefold()
            for name in scope.get("accessible_functions", [])
            if str(name).strip()
        }
        team_functions = {name.casefold() for name in functions_for_team(team_name)}
        return bool(allowed_functions & team_functions)
    if scope.get("legacy_unscoped"):
        return True
    if scope.get("role") in {"Admin", "General Manager"} or scope.get("has_unrestricted_team_access"):
        return True
    accessible = set().union(*(_team_keys(str(team)) for team in scope.get("accessible_teams", [])))
    return bool(_team_keys(team_name) & accessible)


def user_can_access_team_level(scope: dict, team_name: str, performance_level: str) -> bool:
    if scope.get("role") == "Function Viewer":
        return user_can_access_team(scope, team_name)
    if scope.get("legacy_unscoped"):
        return False
    if scope.get("role") in {"Admin", "General Manager"} or scope.get("has_unrestricted_team_access"):
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
    role = scope.get("role")
    if role == "Function Viewer":
        allowed_functions = {
            str(name).strip().casefold()
            for name in scope.get("accessible_functions", [])
            if str(name).strip()
        }
        return [
            record for record in records
            if any(
                function.casefold() in allowed_functions
                for function in functions_for_team(str(_record_value(record, "team", "") or ""))
            )
        ]
    if scope.get("legacy_unscoped"):
        return records
    if role in {"Agent", "Executive"}:
        self_id = str(scope.get("employee_id") or scope.get("user_id") or "")
        return [record for record in records if str(_record_value(record, "employee_id")) == self_id]
    if role == "Manager" and not scope.get("has_unrestricted_team_access"):
        accessible = set().union(*(_team_keys(str(team)) for team in scope.get("accessible_teams", [])))
        return [record for record in records if str(_record_value(record, "team")).lower() in accessible]
    return records


def filter_records_by_team_levels(records, scope: dict):
    """Apply explicit team/level assignments after the broader role scope filter."""
    if scope.get("role") == "Function Viewer":
        return filter_records_by_scope(records, scope)
    if scope.get("role") == "Admin" or scope.get("has_unrestricted_team_access") or scope.get("legacy_unscoped"):
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
