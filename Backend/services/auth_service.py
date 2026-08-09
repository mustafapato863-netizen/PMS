"""Authentication Service
Handles user registration, login, JWT token operations, and account lockouts.
"""

import jwt
import redis
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from config import settings
from models.models import User
from services.password_service import validate_password_strength, hash_password, verify_password
from services.redis_provider import redis_client
from utils.user_identity import humanize_username

logger = logging.getLogger(__name__)

class AuthenticationService:
    """Enterprise authentication service"""

    @staticmethod
    def create_user(db: Session, username: str, email: str, password_raw: str, role: str = "Viewer") -> User:
        """
        Validate password and create a new user.
        """
        # Validate strength
        validate_password_strength(password_raw)

        # Check existing username/email
        existing_username = db.query(User).filter(User.username == username).first()
        if existing_username:
            raise ValueError(f"Username '{username}' is already taken.")

        existing_email = db.query(User).filter(User.email == email).first()
        if existing_email:
            raise ValueError(f"Email '{email}' is already registered.")

        # Hash and save
        hashed = hash_password(password_raw)
        user = User(
            full_name=humanize_username(username),
            username=username,
            email=email,
            password_hash=hashed,
            role=role,
            is_active=True,
            failed_login_attempts=0
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def authenticate_user(db: Session, username: str, password_raw: str) -> str:
        """
        Verify credentials, manage account lockout, update last login, and issue JWT.
        """
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise ValueError("Invalid username or password.")
        if not user.is_active:
            raise ValueError("User account is disabled")

        now = datetime.now(timezone.utc)

        # Check account lockout
        if user.locked_until:
            # If locked_until is offset-naive, make it timezone-aware or vice versa to compare
            locked_until_utc = user.locked_until.replace(tzinfo=timezone.utc) if user.locked_until.tzinfo is None else user.locked_until
            if now < locked_until_utc:
                remaining = int((locked_until_utc - now).total_seconds() / 60) + 1
                raise ValueError(f"Account is temporarily locked. Try again in {remaining} minute(s).")
            else:
                # Lock expired, reset failed attempts
                user.locked_until = None
                user.failed_login_attempts = 0
                db.commit()

        # Verify password
        if not verify_password(password_raw, user.password_hash):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.locked_until = now + timedelta(minutes=15)
                db.commit()
                raise ValueError("Account locked due to multiple failed login attempts. Try again in 15 minutes.")
            db.commit()
            raise ValueError("Invalid username or password.")

        # Success: reset login attempt counters, update last_login
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login = now
        db.commit()

        # Generate JWT token
        token_payload = {
            "user_id": str(user.id),
            "username": user.username,
            "role": user.role,
            "exp": now + timedelta(hours=1)
        }
        token = jwt.encode(token_payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

        # Store session in Redis
        if redis_client:
            try:
                redis_client.set(
                    f"session:{user.id}",
                    user.role,
                    ex=3600
                )
            except Exception as e:
                logger.warning(f"Failed to cache session in Redis: {e}")

        return token

    @staticmethod
    def validate_token(token: str) -> dict:
        """
        Validate JWT signature and expiry.
        """
        try:
            payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
            user_id = payload.get("user_id")

            # Redis session check (if redis is active)
            if redis_client:
                try:
                    session_exists = redis_client.exists(f"session:{user_id}")
                    if not session_exists:
                        # Session expired or logged out
                        raise ValueError("Session has expired or logged out.")
                except redis.RedisError as e:
                    logger.warning(f"Redis session lookup error: {e}. Falling back to JWT trust.")

            return payload
        except jwt.ExpiredSignatureError:
            raise ValueError("Token has expired.")
        except jwt.InvalidTokenError:
            raise ValueError("Invalid token.")

    @staticmethod
    def generate_reset_token(user_id: str) -> str:
        """
        Create a time-limited password reset token (24-hour expiry).
        """
        now = datetime.now(timezone.utc)
        payload = {
            "user_id": str(user_id),
            "type": "reset",
            "exp": now + timedelta(hours=24)
        }
        return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
