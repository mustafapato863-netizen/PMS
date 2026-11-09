from __future__ import annotations

from utils.branch_scope import explicit_branch_key
from utils.regions import first_region


def _record_value(record, field: str, default=""):
    if isinstance(record, dict):
        return record.get(field, default)
    return getattr(record, field, default)


def _related_value(record, relation: str, field: str):
    related = _record_value(record, relation, None)
    if isinstance(related, dict):
        return related.get(field)
    return getattr(related, field, None) if related is not None else None


def _record_team_name(record) -> str:
    team = _record_value(record, "team", "")
    if isinstance(team, dict):
        return str(team.get("name") or team.get("db_name") or "")
    if isinstance(team, str):
        return team
    return str(getattr(team, "name", None) or getattr(team, "db_name", None) or "")


def _record_region(record) -> str:
    return first_region(
        _record_value(record, "region", None),
        _related_value(record, "employee", "region"),
        _related_value(record, "team", "region"),
    ).casefold()


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
    "op dubai",
    "pre-approvals op final shjajm",
    "op sharjah",
    "pre-approvals ip final",
    "pre-approvals ip final dubai",
    "ip final dubai",
    "pre-approvals ip final shjajm",
    "ip sharjah",
    "pre-approvals ip elective",
    "pre-approvals ip elective dubai",
    "ip elective dubai",
}

_PRE_APPROVALS_OP_FINAL_KEYS = {
    "pre-approvals op final",
    "pre-approvals op dubai",
    "op dubai",
    "pre-approvals op final shjajm",
    "op sharjah",
}

_PRE_APPROVALS_IP_FINAL_KEYS = {
    "pre-approvals ip final",
    "pre-approvals ip final dubai",
    "ip final dubai",
    "pre-approvals ip final shjajm",
    "ip sharjah",
}

_PRE_APPROVALS_IP_ELECTIVE_KEYS = {
    "pre-approvals ip elective",
    "pre-approvals ip elective dubai",
    "ip elective dubai",
}

_CALL_CENTER_KEYS = {
    "call center",
    "inbound",
    "outbound",
    "support positions",
    "call center support positions",
}

_ADMINISTRATION_KEYS = {"administration", "offshore admin & management"}

_RCM_KEYS = {
    "rcm",
    "coding",
    "coding egy",
    "submission",
    "submission egy",
    "re-submission",
    "resubmission",
    "re-submission egy",
    "pre-approvals",
    "pre-approvals ip offshore",
    "pre-approvals ip",
    "pre-approvals op final",
    "pre-approvals op dubai",
    "op dubai",
    "pre-approvals op final shjajm",
    "op sharjah",
    "pre-approvals ip final",
    "pre-approvals ip final dubai",
    "ip final dubai",
    "pre-approvals ip final shjajm",
    "ip sharjah",
    "pre-approvals ip elective",
    "pre-approvals ip elective dubai",
    "ip elective dubai",
}


def _exact_team_keys(value: str) -> set[str]:
    """Return 1-to-1 spelling aliases for a single team WITHOUT expanding a parent rollup downward to child teams."""
    normalized = str(value).strip().casefold()
    if normalized in {"pre-approvals op dubai", "op dubai"}:
        return {"pre-approvals op dubai", "op dubai"}
    if normalized in {"pre-approvals op final shjajm", "op sharjah"}:
        return {"pre-approvals op final shjajm", "op sharjah"}
    if normalized in {"pre-approvals ip final dubai", "ip final dubai"}:
        return {"pre-approvals ip final dubai", "ip final dubai"}
    if normalized in {"pre-approvals ip final shjajm", "ip sharjah"}:
        return {"pre-approvals ip final shjajm", "ip sharjah"}
    if normalized in _PRE_APPROVALS_IP_ELECTIVE_KEYS:
        return set(_PRE_APPROVALS_IP_ELECTIVE_KEYS)
    if normalized in {"support positions", "call center support positions"}:
        return {"call center", "support positions", "call center support positions"}
    if normalized in {"rcm", "rcm_management"}:
        return {"rcm", "rcm_management"}
    if normalized in {"resubmission", "re-submission egy"}:
        return {"resubmission", "re-submission egy"}
    if normalized in {
        "crm", "crm_management", "nursing", "nursing_management",
        "pmo", "pmo_management", "finance", "finance_management",
        "marketing", "marketing_management", "pharmacy", "pharmacy_management",
    }:
        base = normalized.removesuffix("_management")
        return {base, f"{base}_management"}
    if normalized in _ADMINISTRATION_KEYS:
        return set(_ADMINISTRATION_KEYS)
    return {normalized}


def _team_keys(value: str) -> set[str]:
    normalized = str(value).strip().casefold()
    if normalized == "pre-approvals":
        return _PRE_APPROVALS_UAE_KEYS
    if normalized == "pre-approvals op final":
        return _PRE_APPROVALS_OP_FINAL_KEYS
    if normalized == "pre-approvals ip final":
        return _PRE_APPROVALS_IP_FINAL_KEYS
    if normalized in _PRE_APPROVALS_IP_ELECTIVE_KEYS:
        return _PRE_APPROVALS_IP_ELECTIVE_KEYS
    if normalized == "call center":
        return _CALL_CENTER_KEYS
    if normalized in {"rcm", "rcm_management"}:
        return _RCM_KEYS | {"rcm_management"}
    return _exact_team_keys(value)


FUNCTION_VIEWER_FUNCTIONS = ("Call Center", "RCM", "Pre-Approvals", "Marketing", "Sales", "CSR", "Pharmacy")
FUNCTION_SCOPED_ROLES = {"Function Viewer", "Function Director"}
GLOBAL_DATA_ROLES = {"Admin", "General Manager", "Performance Team", "Viewer"}
SELF_SCOPED_ROLES = {"Agent", "Executive", "Employee"}


def _normalize_team_level_entry(item) -> str:
    if isinstance(item, (list, tuple)) and len(item) >= 2:
        t = str(item[0] or "").strip().casefold()
        lvl = str(item[1] or "").strip().casefold()
        return f"{t}:{lvl}" if t else ""
    if isinstance(item, str) and ":" in item:
        t, lvl = item.split(":", 1)
        return f"{t.strip().casefold()}:{lvl.strip().casefold()}" if t.strip() else ""
    return str(item or "").strip().casefold()


def canonical_scope_identity(scope: dict | None) -> dict:
    """Build a canonical, deterministic representation of all effective authorization dimensions."""
    if not scope:
        return {}
    role = str(scope.get("role") or scope.get("db_role") or "").strip()
    emp_id = str(scope.get("employee_id") or "").strip()
    is_self_only = bool(scope.get("is_self_only")) or (role in SELF_SCOPED_ROLES)
    return {
        "user_id": str(scope.get("user_id") or "").strip(),
        "role": role,
        "employee_id": emp_id,
        "is_self_only": is_self_only,
        "is_active": bool(scope.get("is_active", True)),
        "legacy_unscoped": bool(scope.get("legacy_unscoped", False)),
        "has_unrestricted_team_access": bool(scope.get("has_unrestricted_team_access", False)),
        "accessible_teams": sorted(
            {
                str(v).strip()
                for v in (scope.get("accessible_teams") or scope.get("allowed_teams") or [])
                if str(v).strip()
            }
        ),
        "accessible_team_levels": sorted(
            {
                norm
                for item in (scope.get("accessible_team_levels") or [])
                if (norm := _normalize_team_level_entry(item))
            }
        ),
        "accessible_functions": sorted(
            {
                str(v).strip()
                for v in (scope.get("accessible_functions") or scope.get("allowed_functions") or [])
                if str(v).strip()
            }
        ),
        "accessible_regions": sorted(
            {
                str(v).strip()
                for v in (scope.get("accessible_regions") or scope.get("allowed_regions") or [])
                if str(v).strip()
            }
        ),
        "accessible_branches": sorted(
            {
                str(v).strip()
                for v in (scope.get("accessible_branches") or scope.get("allowed_branches") or [])
                if str(v).strip()
            }
        ),
    }


# "Functions" are the parent domains that ``_team_keys`` already expands into
# their source teams (the same values the Insights ``team`` filter accepts as
# rollups). A team that is not part of any parent domain (Marketing, Sales,
# CSR, Pharmacy, ...) is its own function, mirroring the
# ``_team_keys`` fallback of an exact team match. Order is broadest first:
# UAE Pre-Approvals teams belong to RCM *and* to the narrower Pre-Approvals
# function, exactly as ``_RCM_KEYS`` and ``_PRE_APPROVALS_UAE_KEYS`` overlap.
_FUNCTION_CALL_CENTER_KEYS = _CALL_CENTER_KEYS | {"inbound uae"}
_FUNCTION_TEAM_KEYS: dict[str, set[str]] = {
    "Call Center": _FUNCTION_CALL_CENTER_KEYS,
    "RCM": _RCM_KEYS,
    "Pre-Approvals": _PRE_APPROVALS_UAE_KEYS,
    "Administration": _ADMINISTRATION_KEYS,
}


def functions_for_team(team_name: str) -> list[str]:
    """Return every function (parent domain) the given team rolls up into."""
    normalized = str(team_name or "").strip()
    if not normalized:
        return []
    key = normalized.casefold()
    if key in {"support positions", "call center support positions"}:
        return ["Call Center"]
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
    norm = str(function_name).strip().casefold()
    if norm == "call center":
        return _team_keys(str(function_name)) | {"inbound uae"}
    return _team_keys(str(function_name))


def selection_team_keys(team_name: str) -> set[str]:
    """Expand a UI rollup, not a grant. Always intersect with user scope first.

    The new RCM Pre-Approvals team includes Offshore as a sub-team. Legacy
    Pre-Approvals grants retain their UAE-only meaning in ``_team_keys``.
    """
    norm = str(team_name).strip().casefold()
    if norm == "inbound":
        return {"inbound", "inbound uae"}
    if norm == "pre-approvals":
        return _PRE_APPROVALS_UAE_KEYS | {"pre-approvals ip offshore"}
    if norm in {"pre-approvals op dubai", "op dubai"}:
        return {"pre-approvals op dubai", "op dubai"}
    if norm in {"pre-approvals op final shjajm", "op sharjah"}:
        return {"pre-approvals op final shjajm", "op sharjah"}
    if norm in {"pre-approvals ip final dubai", "ip final dubai"}:
        return {"pre-approvals ip final dubai", "ip final dubai"}
    if norm in {"pre-approvals ip final shjajm", "ip sharjah"}:
        return {"pre-approvals ip final shjajm", "ip sharjah"}
    if norm in {"pre-approvals ip elective dubai", "ip elective dubai"}:
        return {"pre-approvals ip elective dubai", "ip elective dubai"}
    return _team_keys(team_name)


def user_can_access_team(scope: dict, team_name: str) -> bool:
    role = scope.get("role")
    if role in FUNCTION_SCOPED_ROLES:
        allowed_functions = {
            str(name).strip().casefold()
            for name in scope.get("accessible_functions", [])
            if str(name).strip()
        }
        team_functions = {name.casefold() for name in functions_for_team(team_name)}
        return bool(allowed_functions & team_functions)
    if scope.get("legacy_unscoped"):
        return True
    if role in GLOBAL_DATA_ROLES or scope.get("has_unrestricted_team_access"):
        return True
    if role == "Regional Manager":
        # Opening a team is allowed; its records still intersect the region grant.
        return any(str(value).strip() for value in scope.get("accessible_regions", []))
    if role == "Branch Director":
        # Team-only checks are followed by branch filtering on the records.
        return bool(scope.get("accessible_branches") or scope.get("allowed_branches"))
    accessible = set().union(*(_team_keys(str(team)) for team in scope.get("accessible_teams", [])))
    return bool(_team_keys(team_name) & accessible)


def user_can_access_team_level(scope: dict, team_name: str, performance_level: str) -> bool:
    role = scope.get("role")
    if role in FUNCTION_SCOPED_ROLES:
        return user_can_access_team(scope, team_name)
    if scope.get("legacy_unscoped"):
        return False
    if role in GLOBAL_DATA_ROLES or scope.get("has_unrestricted_team_access"):
        return True
    if role in {"Regional Manager", "Branch Director"}:
        return user_can_access_team(scope, team_name)
    if not user_can_access_team(scope, team_name):
        return False
    configured = {
        (team_key, str(level))
        for team, level in scope.get("accessible_team_levels", [])
        for team_key in _team_keys(str(team))
    }
    target_keys = _exact_team_keys(team_name)
    team_levels = {str(level).strip().casefold() for team, level in configured if team in target_keys}
    return not team_levels or str(performance_level or "Employee").strip().casefold() in team_levels


def user_can_access_region(scope: dict, region: str | None) -> bool:
    """Check an explicitly attributed region without inferring it from team access."""
    region_key = str(region or "").strip().casefold()
    allowed_regions = {
        str(value).strip().casefold()
        for value in scope.get("accessible_regions", [])
        if str(value).strip()
    }
    return bool(region_key and region_key in allowed_regions)


def filter_records_by_scope(records, scope: dict):
    role = scope.get("role")
    if role in FUNCTION_SCOPED_ROLES:
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
    if role == "Branch Director":
        allowed_branches = {str(value).strip().casefold() for value in (scope.get("accessible_branches") or scope.get("allowed_branches") or [])}
        scoped_records = []
        for record in records:
            branch = str(_record_value(record, "branch_key", "") or "").strip().casefold()
            branch = branch or str(explicit_branch_key(record) or "").strip().casefold()
            if branch and branch in allowed_branches:
                scoped_records.append(record)
        return scoped_records
    if role == "Regional Manager":
        allowed_regions = {
            str(value).strip().casefold()
            for value in scope.get("accessible_regions", [])
            if str(value).strip()
        }
        return [
            record for record in records
            if _record_region(record) in allowed_regions
        ]
    if role in SELF_SCOPED_ROLES:
        self_id = str(scope.get("employee_id") or scope.get("user_id") or "")
        return [record for record in records if str(_record_value(record, "employee_id")) == self_id]
    if role == "Manager" and not scope.get("has_unrestricted_team_access"):
        accessible = set().union(*(_team_keys(str(team)) for team in scope.get("accessible_teams", [])))
        return filter_records_by_team_levels(
            [
                record
                for record in records
                if bool(_exact_team_keys(str(_record_value(record, "team"))) & accessible)
            ],
            scope,
        )
    if role in GLOBAL_DATA_ROLES or role == "Manager":
        return records
    return []


def filter_records_by_team_levels(records, scope: dict):
    """Apply explicit team/level assignments after the broader role scope filter."""
    if scope.get("role") in FUNCTION_SCOPED_ROLES | {"Regional Manager", "Branch Director"}:
        return filter_records_by_scope(records, scope)
    if scope.get("role") in GLOBAL_DATA_ROLES or scope.get("has_unrestricted_team_access") or scope.get("legacy_unscoped"):
        return records
    configured = {
        (team_key, str(level).strip().casefold())
        for team, level in scope.get("accessible_team_levels", [])
        for team_key in _team_keys(str(team))
    }
    if not configured:
        return records
    return [
        record
        for record in records
        if any(
            (team_key, str(_record_value(record, "performance_level") or "Employee").strip().casefold()) in configured
            for team_key in _exact_team_keys(str(_record_value(record, "team")))
        )
    ]
