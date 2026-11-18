"""UserIdentityPassport for PMS AI.

A frozen dataclass built once per request, carrying the caller's identity,
persona tier, employee linkage, and authorized scope. Injected into every
AI pipeline call so tools and prompts are always scope-aware.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID


class PersonaTier(str, Enum):
    SELF_ONLY = "self_only"
    SCOPED_MANAGER = "scoped_manager"
    GLOBAL_EXEC = "global_exec"


@dataclass(frozen=True)
class UserIdentityPassport:
    """Immutable identity passport for an AI request."""

    user_id: str
    username: str
    role: str
    persona_tier: PersonaTier
    employee_pk: str | None  # UUID as string, for PerformanceRecord FK
    employee_code: str | None  # String, for User↔Employee link
    is_linked_employee: bool
    authorized_teams: list[str] = field(default_factory=list)
    authorized_branches: list[str] = field(default_factory=list)
    authorized_departments: list[str] = field(default_factory=list)
    has_unrestricted_team_access: bool = False

    def to_xml(self) -> str:
        """Serialize to compact XML block (≤ 200 tokens)."""
        teams = ",".join(self.authorized_teams) if self.authorized_teams else "none"
        branches = ",".join(self.authorized_branches) if self.authorized_branches else "none"
        depts = ",".join(self.authorized_departments) if self.authorized_departments else "none"
        return (
            f'<CALLER_PASSPORT role="{self.role}" persona="{self.persona_tier.value}" '
            f'employee_code="{self.employee_code or "none"}" linked="{str(self.is_linked_employee).lower()}" '
            f'teams="[{teams}]" branches="[{branches}]" departments="[{depts}]" '
            f'unrestricted="{str(self.has_unrestricted_team_access).lower()}"/>'
        )


def build_passport(scope: dict[str, Any], username: str = "") -> UserIdentityPassport:
    """Build a UserIdentityPassport from an RBAC scope dict.

    PersonaTier resolution:
    - Admin, Executive (with unrestricted) → GLOBAL_EXEC
    - Manager, Regional Manager → SCOPED_MANAGER
    - Agent, Employee → SELF_ONLY
    """
    role = str(scope.get("role") or "").strip()
    user_id = str(scope.get("user_id") or "").strip()
    employee_code = str(scope.get("employee_id") or "").strip() or None

    # Determine persona tier
    if role in ("Admin", "General Manager", "Performance Team"):
        persona_tier = PersonaTier.GLOBAL_EXEC
    elif role in ("Executive",) and scope.get("has_unrestricted_team_access"):
        persona_tier = PersonaTier.GLOBAL_EXEC
    elif role in ("Manager", "Regional Manager", "Branch Director", "Function Director", "Function Viewer"):
        persona_tier = PersonaTier.SCOPED_MANAGER
    else:
        persona_tier = PersonaTier.SELF_ONLY

    # employee_pk: try to resolve from scope or leave None
    # The spec says employee_pk is a UUID FK to Employee.id
    # We store employee_code (String) from scope; employee_pk requires a DB lookup
    employee_pk = None  # Resolved separately if needed

    is_linked = bool(employee_code) and persona_tier == PersonaTier.SELF_ONLY

    # For non-self-only, employee linkage is less critical
    if persona_tier != PersonaTier.SELF_ONLY and employee_code:
        is_linked = True

    return UserIdentityPassport(
        user_id=user_id,
        username=username or str(scope.get("username") or ""),
        role=role,
        persona_tier=persona_tier,
        employee_pk=employee_pk,
        employee_code=employee_code,
        is_linked_employee=is_linked,
        authorized_teams=list(scope.get("accessible_teams") or []),
        authorized_branches=list(scope.get("accessible_branches") or []),
        authorized_departments=list(scope.get("accessible_functions") or []),
        has_unrestricted_team_access=bool(scope.get("has_unrestricted_team_access")),
    )
