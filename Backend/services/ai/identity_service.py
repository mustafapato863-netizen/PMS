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
        """Serialize to compact XML block (≤ 200 tokens) with attribute escaping."""
        def _esc(val: str) -> str:
            return (
                val.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )

        teams = ",".join(_esc(str(t)) for t in self.authorized_teams[:8]) if self.authorized_teams else "none"
        branches = ",".join(_esc(str(b)) for b in self.authorized_branches[:8]) if self.authorized_branches else "none"
        depts = ",".join(_esc(str(d)) for d in self.authorized_departments[:8]) if self.authorized_departments else "none"
        return (
            f'<CALLER_PASSPORT role="{_esc(self.role)}" persona="{self.persona_tier.value}" '
            f'employee_code="{_esc(self.employee_code or "none")}" linked="{str(self.is_linked_employee).lower()}" '
            f'teams="[{teams}]" branches="[{branches}]" departments="[{depts}]" '
            f'unrestricted="{str(self.has_unrestricted_team_access).lower()}"/>'
        )


def build_passport(
    scope: dict[str, Any],
    username: str = "",
    db: Any | None = None,
) -> UserIdentityPassport:
    """Build a UserIdentityPassport from an RBAC scope dict.

    PersonaTier resolution:
    - Admin, General Manager, Performance Team, Executive → GLOBAL_EXEC
    - Manager, Regional Manager, Branch Director, Function Director, Function Viewer → SCOPED_MANAGER
    - Agent, Employee (and fallback) → SELF_ONLY

    When ``db`` is provided and ``employee_code`` is present, resolves
    ``employee_pk`` (Employee.id UUID) so callers have both the String code and
    the UUID FK required by PerformanceRecord / Action / PerformancePlan.
    """
    role = str(scope.get("role") or "").strip()
    user_id = str(scope.get("user_id") or "").strip()
    employee_code = str(scope.get("employee_id") or "").strip() or None

    # Determine persona tier (Executive is GLOBAL_EXEC read-only per spec §1.5)
    if role in ("Admin", "General Manager", "Performance Team", "Executive"):
        persona_tier = PersonaTier.GLOBAL_EXEC
    elif role in ("Manager", "Regional Manager", "Branch Director", "Function Director", "Function Viewer"):
        persona_tier = PersonaTier.SCOPED_MANAGER
    else:
        persona_tier = PersonaTier.SELF_ONLY

    # Resolve employee_pk (UUID as string) from scope or DB lookup
    raw_pk = scope.get("employee_pk")
    employee_pk: str | None = str(raw_pk).strip() if raw_pk else None
    if employee_pk is None and employee_code and db is not None:
        try:
            from models.models import Employee

            emp = (
                db.query(Employee.id)
                .filter(Employee.employee_id == employee_code, Employee.is_active.is_(True))
                .first()
            )
            if emp is not None and emp[0] is not None:
                employee_pk = str(emp[0])
        except Exception:
            employee_pk = None

    is_linked = bool(employee_pk or employee_code)

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
