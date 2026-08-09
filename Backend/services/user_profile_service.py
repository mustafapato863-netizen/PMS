from sqlalchemy.orm import Session

from models.models import User
from repositories.user_repository import UserRepository
from services.password_service import hash_password, validate_password_strength, verify_password


class UserProfileNotFoundError(ValueError):
    """Raised when the authenticated user no longer exists."""


class CurrentPasswordInvalidError(ValueError):
    """Raised when the supplied current password does not match."""


class PasswordReuseError(ValueError):
    """Raised when a user attempts to reuse the current password."""


class UserProfileService:
    """Own self-service profile rules and their transaction boundaries."""

    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db, User)

    def update_full_name(self, user_id: str, full_name: str) -> User:
        normalized = full_name.strip()
        if not normalized:
            raise ValueError("Full name cannot be blank.")

        try:
            user = self.users.set_full_name(user_id, normalized)
            if not user:
                raise UserProfileNotFoundError("User not found.")
            self.db.commit()
            self.db.refresh(user)
            return user
        except Exception:
            self.db.rollback()
            raise

    def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> None:
        try:
            user = self.users.get_by_id(user_id, include_deleted=True)
            if not user:
                raise UserProfileNotFoundError("User not found.")
            if not verify_password(current_password, user.password_hash):
                raise CurrentPasswordInvalidError("Current password is incorrect.")
            validate_password_strength(new_password)
            if verify_password(new_password, user.password_hash):
                raise PasswordReuseError("New password must be different from the current password.")

            self.users.set_password_hash(user, hash_password(new_password))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
