"""Deployment-wide switch for PMS AI.

A missing row or an unreadable table means AI is off. Existing tests replace
``is_ai_enabled`` so chat suites keep running; production uses ``read_ai_enabled``.
"""

from __future__ import annotations

import logging
import os
import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from config import settings
from config.database import get_db
from models.models import ProductSetting
from services.audit_service import AuditService

logger = logging.getLogger(__name__)

AI_SETTING_KEY = "ai_enabled"
AI_CORRECTIVE_ACTION_PILOT_KEY = "ai_corrective_action_pilot_enabled"
AI_PILOT_ROLE = "Admin"


def _legacy_role_header_allowed() -> bool:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    return (
        settings.APP_ENV in {"development", "test"}
        and os.environ.get("ALLOW_LEGACY_API_ACCESS") == "1"
    )


def read_ai_enabled(db: Session) -> bool:
    try:
        row = db.query(ProductSetting).filter(ProductSetting.key == AI_SETTING_KEY).one_or_none()
    except SQLAlchemyError:
        db.rollback()
        logger.warning("PMS AI setting could not be read; treating AI as off")
        return False
    return bool(row and row.enabled)


def is_ai_enabled(db: Session) -> bool:
    return read_ai_enabled(db)


def set_ai_enabled(db: Session, enabled: bool, user_id: str | None) -> bool:
    row = db.query(ProductSetting).filter(ProductSetting.key == AI_SETTING_KEY).one_or_none()
    previous = bool(row.enabled) if row is not None else False
    actor_id = None
    if user_id:
        try:
            actor_id = uuid.UUID(str(user_id))
        except (TypeError, ValueError):
            actor_id = None
    if row is None:
        row = ProductSetting(key=AI_SETTING_KEY, enabled=enabled, updated_by_user_id=actor_id)
        db.add(row)
    else:
        row.enabled = enabled
        row.updated_by_user_id = actor_id
    db.commit()
    try:
        AuditService.log_operation(
            db,
            "product_settings",
            "UPDATE",
            None,
            {"key": AI_SETTING_KEY, "enabled": previous},
            {"key": AI_SETTING_KEY, "enabled": enabled},
            str(actor_id) if actor_id else None,
        )
    except Exception:
        logger.exception("PMS AI setting was saved but the audit row was not")
    return enabled


def require_ai_enabled(db: Session = Depends(get_db)) -> None:
    if not is_ai_enabled(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="PMS AI is turned off.",
        )


def read_ai_corrective_action_pilot_enabled(db: Session) -> bool:
    """Separate pilot switch for contextual corrective-action suggestions.

    Independent of the standalone AI chat switch (``ai_enabled``): enabling
    this pilot must never expose standalone chat. A missing row or an
    unreadable table means the pilot is off.
    """
    try:
        row = db.query(ProductSetting).filter(ProductSetting.key == AI_CORRECTIVE_ACTION_PILOT_KEY).one_or_none()
    except SQLAlchemyError:
        db.rollback()
        logger.warning("PMS AI corrective-action pilot setting could not be read; treating the pilot as off")
        return False
    return bool(row and row.enabled)


def set_ai_corrective_action_pilot_enabled(db: Session, enabled: bool, user_id: str | None) -> bool:
    row = db.query(ProductSetting).filter(ProductSetting.key == AI_CORRECTIVE_ACTION_PILOT_KEY).one_or_none()
    previous = bool(row.enabled) if row is not None else False
    actor_id = None
    if user_id:
        try:
            actor_id = uuid.UUID(str(user_id))
        except (TypeError, ValueError):
            actor_id = None
    if row is None:
        row = ProductSetting(key=AI_CORRECTIVE_ACTION_PILOT_KEY, enabled=enabled, updated_by_user_id=actor_id)
        db.add(row)
    else:
        row.enabled = enabled
        row.updated_by_user_id = actor_id
    db.commit()
    try:
        AuditService.log_operation(
            db,
            "product_settings",
            "UPDATE",
            None,
            {"key": AI_CORRECTIVE_ACTION_PILOT_KEY, "enabled": previous},
            {"key": AI_CORRECTIVE_ACTION_PILOT_KEY, "enabled": enabled},
            str(actor_id) if actor_id else None,
        )
    except Exception:
        logger.exception("PMS AI corrective-action pilot setting was saved but the audit row was not")
    return enabled


def require_ai_corrective_action_pilot_enabled(db: Session = Depends(get_db)) -> None:
    """Gate for corrective-action pilot routes. Standalone chat stays separate."""
    if not read_ai_corrective_action_pilot_enabled(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The corrective-action pilot is turned off.",
        )


def request_role(request: Request) -> str:
    """Role attached by auth middleware, otherwise the legacy test header when permitted."""
    user = getattr(request.state, "user", None)
    if isinstance(user, dict) and user.get("role"):
        return str(user.get("role"))
    if _legacy_role_header_allowed():
        header = request.headers.get("x-user-role")
        if header:
            return header
    return "Viewer"


def require_ai_admin(request: Request) -> str:
    """Pilot gate. Non-Admin is rejected even when the product switch is on."""
    role = request_role(request)
    if role != AI_PILOT_ROLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="PMS AI is limited to administrators during the pilot.",
        )
    return role


def require_ai_diagnostic_session(request: Request) -> None:
    """Reject callers with no session (or legacy test header when permitted).

    The Admin decision itself stays in ``require_ai_admin``. This only separates
    an anonymous request from a signed-in non-Admin.
    """
    user = getattr(request.state, "user", None)
    has_session = isinstance(user, dict) and bool(str(user.get("user_id") or user.get("role") or "").strip())
    if has_session:
        return
    if _legacy_role_header_allowed() and (
        request.headers.get("x-user-role") or request.headers.get("authorization")
    ):
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )
