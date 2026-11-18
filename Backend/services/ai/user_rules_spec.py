"""User Rules Spec builder for AI assistant.

Builds a structured description of who the authenticated user is and what
they can/cannot access, derived from the RBAC scope dict. Injected into
the assistant's context for every turn so the model never leaks data
outside the user's permissions.
"""

from __future__ import annotations

from typing import Any


def build_user_rules_spec(scope: dict[str, Any]) -> dict[str, Any]:
    """Build a structured User Rules Spec from an RBAC scope dict.

    Returns a dict with:
    - identity: who the user is
    - permissions: what they can access
    - restrictions: what they cannot access
    - is_self_only: whether they are an employee/agent (self-service only)
    - summary_text: human-readable summary for prompt injection
    """
    role = str(scope.get("role") or "").strip()
    user_id = str(scope.get("user_id") or "").strip()
    employee_id = str(scope.get("employee_id") or "").strip() or None
    has_unrestricted = bool(scope.get("has_unrestricted_team_access"))
    is_self_only = bool(scope.get("is_self_only"))
    accessible_teams = [str(t).strip() for t in (scope.get("accessible_teams") or []) if str(t).strip()]
    accessible_functions = [str(f).strip() for f in (scope.get("accessible_functions") or []) if str(f).strip()]
    accessible_regions = [str(r).strip() for r in (scope.get("accessible_regions") or []) if str(r).strip()]
    accessible_branches = [str(b).strip() for b in (scope.get("accessible_branches") or []) if str(b).strip()]
    active_team_names = [str(t).strip() for t in (scope.get("active_team_names") or []) if str(t).strip()]

    # Determine restrictions
    restricted_teams = []
    if not has_unrestricted:
        restricted_teams = [t for t in active_team_names if t not in accessible_teams]

    spec = {
        "identity": {
            "user_id": user_id,
            "role": role,
            "employee_id": employee_id,
            "is_self_only": is_self_only,
        },
        "permissions": {
            "has_unrestricted_team_access": has_unrestricted,
            "accessible_teams": accessible_teams,
            "accessible_functions": accessible_functions,
            "accessible_regions": accessible_regions,
            "accessible_branches": accessible_branches,
            "active_team_names": active_team_names,
        },
        "restrictions": {
            "restricted_teams": restricted_teams,
            "cannot_access_other_employees": is_self_only,
            "cannot_access_unauthorized_teams": not has_unrestricted,
        },
    }

    # Build human-readable summary for prompt injection
    lines = [f"User: role={role}"]
    if employee_id:
        lines.append(f"Employee ID: {employee_id}")
    if has_unrestricted:
        lines.append("Access: ALL teams (unrestricted)")
    else:
        if accessible_teams:
            lines.append(f"Access: teams={accessible_teams}")
        if accessible_functions:
            lines.append(f"Access: functions={accessible_functions}")
        if accessible_regions:
            lines.append(f"Access: regions={accessible_regions}")
        if accessible_branches:
            lines.append(f"Access: branches={accessible_branches}")
    if is_self_only:
        lines.append("Restriction: self-only (can only view own data)")
    if restricted_teams:
        lines.append(f"Restricted: cannot access {restricted_teams}")

    spec["summary_text"] = "\n".join(lines)
    return spec


def get_user_rules_spec_text(scope: dict[str, Any]) -> str:
    """Return a human-readable User Rules Spec string for prompt injection."""
    spec = build_user_rules_spec(scope)
    return spec["summary_text"]


def is_self_service_query(scope: dict[str, Any]) -> bool:
    """Check if the user is an employee/agent who can only access their own data."""
    return bool(scope.get("is_self_only")) and bool(scope.get("employee_id"))


def resolve_self_employee_id(scope: dict[str, Any]) -> str | None:
    """Resolve the employee_id for a self-service query from the user's scope.

    Returns the employee_id if the user is self-only and has an employee_id,
    None otherwise.
    """
    if not is_self_service_query(scope):
        return None
    eid = str(scope.get("employee_id") or "").strip()
    return eid if eid else None
