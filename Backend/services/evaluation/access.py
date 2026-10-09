"""Server-side limits for evaluation versions, jobs, previews, and exports."""

from __future__ import annotations

from utils.report_scope import user_can_access_team


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


DRAFT_ROLES = {"Admin", "Performance Team"}
PREVIEW_ROLES = {"Admin", "Performance Team"}
READ_VERSION_ROLES = {"Admin", "General Manager", "Performance Team"}
APPLIED_DENY = {"Employee", "Agent", "Executive"}
SCOPED_EVIDENCE_ROLES = {"Branch Director", "Regional Manager"}


def require_action(scope: dict | None, team_name: str, action: str) -> None:
    """Deny from the caller's current grants. A revoked assignment fails this check."""
    scope = scope or {}
    role = str(scope.get("role") or "")
    if action in {"approve", "apply", "rollback"} and role != "Admin":
        raise AccessDenied("Approval and apply are limited to Admin.")
    if action == "draft" and role not in DRAFT_ROLES:
        raise AccessDenied("Access denied")
    if action in {"preview", "export", "job"} and role not in PREVIEW_ROLES:
        raise AccessDenied("Access denied")
    if action == "version" and role not in READ_VERSION_ROLES:
        raise AccessDenied("Access denied")
    if role in SCOPED_EVIDENCE_ROLES and action in {"version", "preview", "export", "job", "draft", "approve", "apply", "rollback"}:
        raise AccessDenied("Access denied")
    if role in APPLIED_DENY and action != "applied":
        raise AccessDenied("Access denied")
    if action == "applied" and role in APPLIED_DENY:
        return
    if scope.get("legacy_unscoped"):
        raise AccessDenied("Access denied")
    if not user_can_access_team(scope, team_name):
        raise AccessDenied("Access denied")
