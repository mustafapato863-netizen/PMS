"""Authentication and durable browser-session services."""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hmac import compare_digest

import jwt
import redis
from sqlalchemy.orm import Session

from config import settings
from models.models import RefreshSession, User
from services.password_service import hash_password, validate_password_strength, verify_password
from services.redis_provider import redis_client
from utils.user_identity import humanize_username

logger = logging.getLogger(__name__)


class RefreshTokenError(ValueError):
    """Base error for invalid or unusable refresh credentials."""


class RefreshTokenReuseError(RefreshTokenError):
    """Raised when a rotated refresh token is presented again."""


class InvalidCsrfTokenError(RefreshTokenError):
    """Raised when a cookie-authenticated request presents the wrong CSRF value."""


@dataclass(frozen=True)
class IssuedSession:
    session_id: uuid.UUID
    access_token: str
    refresh_token: str
    csrf_token: str
    access_expires_in: int
    refresh_expires_at: datetime
    user: User


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _new_secret() -> str:
    return secrets.token_urlsafe(48)


class AuthenticationService:
    """Credential verification, JWT issuance, and refresh-session rotation."""

    @staticmethod
    def create_user(db: Session, username: str, email: str, password_raw: str, role: str = "Viewer") -> User:
        validate_password_strength(password_raw)

        if db.query(User).filter(User.username == username).first():
            raise ValueError(f"Username '{username}' is already taken.")
        if db.query(User).filter(User.email == email).first():
            raise ValueError(f"Email '{email}' is already registered.")

        user = User(
            full_name=humanize_username(username),
            username=username,
            email=email,
            password_hash=hash_password(password_raw),
            role=role,
            is_active=True,
            failed_login_attempts=0,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def _authenticate_user_record(db: Session, username: str, password_raw: str) -> tuple[User, datetime]:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise ValueError("Invalid username or password.")
        if not user.is_active:
            raise ValueError("User account is disabled")

        now = _now()
        if user.locked_until:
            locked_until = _aware(user.locked_until)
            if now < locked_until:
                remaining = int((locked_until - now).total_seconds() / 60) + 1
                raise ValueError(f"Account is temporarily locked. Try again in {remaining} minute(s).")
            user.locked_until = None
            user.failed_login_attempts = 0
            db.commit()

        if not verify_password(password_raw, user.password_hash):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.locked_until = now + timedelta(minutes=15)
                db.commit()
                raise ValueError("Account locked due to multiple failed login attempts. Try again in 15 minutes.")
            db.commit()
            raise ValueError("Invalid username or password.")

        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login = now
        db.commit()
        return user, now

    @staticmethod
    def _access_token(user: User, now: datetime, session_id: uuid.UUID | None = None) -> str:
        payload = {
            "user_id": str(user.id),
            "sub": user.username,
            "username": user.username,
            "role": user.role,
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
        }
        if session_id is not None:
            payload["sid"] = str(session_id)
        return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    @staticmethod
    def _cache_session(session_key: str, role: str, ttl_seconds: int) -> None:
        if not redis_client:
            return
        try:
            redis_client.set(session_key, role, ex=ttl_seconds)
        except redis.RedisError as exc:
            logger.warning("Failed to cache authentication session: %s", exc)

    @staticmethod
    def _delete_cached_session(session_id: uuid.UUID | str) -> None:
        if not redis_client:
            return
        try:
            redis_client.delete(f"session:{session_id}")
        except redis.RedisError as exc:
            logger.warning("Failed to clear authentication session cache: %s", exc)

    @staticmethod
    def authenticate_user(db: Session, username: str, password_raw: str) -> str:
        """Legacy service contract used by existing non-browser callers/tests."""
        user, now = AuthenticationService._authenticate_user_record(db, username, password_raw)
        token = AuthenticationService._access_token(user, now)
        AuthenticationService._cache_session(
            f"session:{user.id}",
            user.role,
            settings.JWT_EXPIRE_MINUTES * 60,
        )
        return token

    @staticmethod
    def authenticate_user_with_session(
        db: Session,
        username: str,
        password_raw: str,
        *,
        remember_me: bool = False,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> IssuedSession:
        user, now = AuthenticationService._authenticate_user_record(db, username, password_raw)
        return AuthenticationService._create_session(
            db,
            user,
            now=now,
            remember_me=remember_me,
            user_agent=user_agent,
            ip_address=ip_address,
        )

    @staticmethod
    def _create_session(
        db: Session,
        user: User,
        *,
        now: datetime,
        remember_me: bool,
        user_agent: str | None,
        ip_address: str | None,
        family_id: uuid.UUID | None = None,
        parent_session_id: uuid.UUID | None = None,
        commit: bool = True,
    ) -> IssuedSession:
        refresh_token = _new_secret()
        csrf_token = _new_secret()
        session_id = uuid.uuid4()
        session_family_id = family_id or uuid.uuid4()
        refresh_lifetime = (
            timedelta(days=settings.AUTH_REMEMBER_SESSION_DAYS)
            if remember_me
            else timedelta(hours=settings.AUTH_REFRESH_SESSION_HOURS)
        )
        refresh_expires_at = now + refresh_lifetime
        session = RefreshSession(
            id=session_id,
            user_id=user.id,
            family_id=session_family_id,
            token_hash=_hash_secret(refresh_token),
            csrf_token_hash=_hash_secret(csrf_token),
            parent_session_id=parent_session_id,
            remember_me=remember_me,
            expires_at=refresh_expires_at,
            user_agent=(user_agent or "")[:512] or None,
            ip_address=ip_address,
        )
        db.add(session)
        db.flush()

        access_token = AuthenticationService._access_token(user, now, session_id=session.id)
        if commit:
            db.commit()
            AuthenticationService._cache_session(
                f"session:{session.id}",
                user.role,
                max(1, int((refresh_expires_at - now).total_seconds())),
            )
        return IssuedSession(
            session_id=session.id,
            access_token=access_token,
            refresh_token=refresh_token,
            csrf_token=csrf_token,
            access_expires_in=settings.JWT_EXPIRE_MINUTES * 60,
            refresh_expires_at=refresh_expires_at,
            user=user,
        )

    @staticmethod
    def rotate_refresh_token(
        db: Session,
        refresh_token: str,
        *,
        csrf_token: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> IssuedSession:
        if not refresh_token:
            raise RefreshTokenError("Refresh session is missing.")

        now = _now()
        session = (
            db.query(RefreshSession)
            .filter(RefreshSession.token_hash == _hash_secret(refresh_token))
            .with_for_update()
            .first()
        )
        if not session:
            raise RefreshTokenError("Refresh session is invalid.")

        if session.revoked_at is not None:
            AuthenticationService._revoke_family(db, session.family_id, "refresh_token_reuse", now)
            raise RefreshTokenReuseError("Refresh session reuse detected.")

        if _aware(session.expires_at) <= now:
            session.revoked_at = now
            session.revocation_reason = "expired"
            db.commit()
            AuthenticationService._delete_cached_session(session.id)
            raise RefreshTokenError("Refresh session has expired.")

        if not csrf_token or not compare_digest(session.csrf_token_hash, _hash_secret(csrf_token)):
            raise InvalidCsrfTokenError("Invalid CSRF token.")

        user = db.query(User).filter(User.id == session.user_id).first()
        if not user or not user.is_active:
            session.revoked_at = now
            session.revocation_reason = "user_inactive"
            db.commit()
            AuthenticationService._delete_cached_session(session.id)
            raise RefreshTokenError("User account is disabled.")

        session.last_used_at = now
        rotated = AuthenticationService._create_session(
            db,
            user,
            now=now,
            remember_me=session.remember_me,
            user_agent=user_agent or session.user_agent,
            ip_address=ip_address or session.ip_address,
            family_id=session.family_id,
            parent_session_id=session.id,
            commit=False,
        )
        session.revoked_at = now
        session.revocation_reason = "rotated"
        session.replaced_by_session_id = rotated.session_id
        db.commit()
        AuthenticationService._cache_session(
            f"session:{rotated.session_id}",
            user.role,
            max(1, int((rotated.refresh_expires_at - now).total_seconds())),
        )
        AuthenticationService._delete_cached_session(session.id)
        return rotated

    @staticmethod
    def revoke_legacy_session(user_id: str | uuid.UUID) -> None:
        """Invalidate the pre-refresh Redis session during compatibility rollout."""
        AuthenticationService._delete_cached_session(user_id)

    @staticmethod
    def _revoke_family(db: Session, family_id: uuid.UUID, reason: str, now: datetime) -> None:
        sessions = db.query(RefreshSession).filter(
            RefreshSession.family_id == family_id,
            RefreshSession.revoked_at.is_(None),
        ).all()
        for session in sessions:
            session.revoked_at = now
            session.revocation_reason = reason
            AuthenticationService._delete_cached_session(session.id)
        db.commit()

    @staticmethod
    def revoke_session(
        db: Session,
        *,
        refresh_token: str | None = None,
        session_id: str | None = None,
        csrf_token: str | None = None,
        reason: str = "logout",
    ) -> None:
        if refresh_token:
            session = db.query(RefreshSession).filter(
                RefreshSession.token_hash == _hash_secret(refresh_token),
            ).first()
        elif session_id:
            session = db.query(RefreshSession).filter(RefreshSession.id == session_id).first()
        else:
            session = None
        if not session:
            return
        if refresh_token and (not csrf_token or not compare_digest(session.csrf_token_hash, _hash_secret(csrf_token))):
            raise InvalidCsrfTokenError("Invalid CSRF token.")
        if session.revoked_at is None:
            session.revoked_at = _now()
            session.revocation_reason = reason
            db.commit()
        AuthenticationService._delete_cached_session(session.id)

    @staticmethod
    def revoke_all_sessions(db: Session, user_id: str | uuid.UUID, reason: str = "password_changed") -> None:
        normalized_user_id: uuid.UUID | str = user_id
        if isinstance(user_id, str):
            try:
                normalized_user_id = uuid.UUID(user_id)
            except ValueError:
                normalized_user_id = user_id
        sessions = db.query(RefreshSession).filter(
            RefreshSession.user_id == normalized_user_id,
            RefreshSession.revoked_at.is_(None),
        ).all()
        now = _now()
        for session in sessions:
            session.revoked_at = now
            session.revocation_reason = reason
            AuthenticationService._delete_cached_session(session.id)
        db.commit()

    @staticmethod
    def validate_token(token: str) -> dict:
        """Validate an access JWT while retaining legacy token compatibility."""
        try:
            payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
            if payload.get("type") not in (None, "access"):
                raise ValueError("Invalid token type.")
            user_id = payload.get("user_id")
            if not user_id:
                raise ValueError("Invalid token.")

            session_id = payload.get("sid")
            session_key = f"session:{session_id or user_id}"
            if redis_client:
                try:
                    if not redis_client.exists(session_key):
                        raise ValueError("Session has expired or logged out.")
                except redis.RedisError as exc:
                    logger.warning("Redis session lookup error: %s. Falling back to JWT trust.", exc)
            return payload
        except jwt.ExpiredSignatureError as exc:
            raise ValueError("Token has expired.") from exc
        except jwt.InvalidTokenError as exc:
            raise ValueError("Invalid token.") from exc

    @staticmethod
    def generate_reset_token(user_id: str) -> str:
        now = _now()
        payload = {
            "user_id": str(user_id),
            "type": "reset",
            "exp": now + timedelta(hours=24),
        }
        return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
