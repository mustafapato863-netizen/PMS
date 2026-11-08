"""Deployment-wide switch for PMS AI.

A missing row or an unreadable table means AI is off. Existing tests replace
``is_ai_enabled`` so chat suites keep running; production uses ``read_ai_enabled``.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from config.database import get_db
from models.models import ProductSetting
from services.audit_service import AuditService

logger = logging.getLogger(__name__)

AI_SETTING_KEY = "ai_enabled"


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
