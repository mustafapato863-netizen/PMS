"""Server-side limits for evaluation settings and applied evidence reads."""

from __future__ import annotations

from utils.report_scope import SELF_SCOPED_ROLES, user_can_access_team_level


class EvaluationError(Exception):
    status_code = 422

    def __init__(self, message: str, **data):
        super().__init__(message)
        self.message = message
        self.data = data


class AccessDenied(EvaluationError):
    status_code = 403


class TargetConflict(EvaluationError):
    status_code = 409


class SchemaIncomplete(EvaluationError):
    status_code = 503


MANAGEMENT_ACTIONS = {
    "catalog",
    "draft",
    "version",
    "preview",
    "export",
    "job",
    "approve",
    "apply",
    "rollback",
}


def require_action(scope: dict | None, team_name: str, action: str, performance_level: str | None = None) -> None:
    """Deny from the caller's current grants. A revoked assignment fails this check.

    Admin alone may manage evaluation settings. Ordinary applied reads use the
    canonical team, performance level, and row scope. They are not Admin-only.
    """
    scope = scope or {}
    role = str(scope.get("role") or "")
    if scope.get("legacy_unscoped"):
        raise AccessDenied("Access denied")
    if action in MANAGEMENT_ACTIONS:
        if role != "Admin":
            raise AccessDenied("Evaluation settings are limited to Admin.")
        return
    if action != "applied":
        raise AccessDenied("Access denied")
    if role in SELF_SCOPED_ROLES:
        if not str(scope.get("employee_id") or "").strip():
            raise AccessDenied("Access denied")
        return
    if not performance_level or not user_can_access_team_level(scope, team_name, performance_level):
        raise AccessDenied("Access denied")
