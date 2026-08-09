from sqlalchemy.orm import Session
from repositories.base_repository import BaseRepository
from models.models import User
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class UserRepository(BaseRepository[User]):
    """Repository for User model"""
    
    def get_by_username(self, username: str) -> User:
        """Get user by username"""
        return self.db.query(User).filter(User.username == username).first()
    
    def get_by_email(self, email: str) -> User:
        """Get user by email"""
        return self.db.query(User).filter(User.email == email).first()
    
    def get_by_role(self, role: str) -> list:
        """Get all users with specific role"""
        return self.db.query(User).filter(User.role == role).all()
    
    def get_active_users(self) -> list:
        """Get all active users"""
        return self.db.query(User).filter(User.is_active == True).all()
    
    def count_active(self) -> int:
        """Count active users"""
        return self.db.query(User).filter(User.is_active == True).count()
    
    def count_by_role(self, role: str) -> int:
        """Count users by role"""
        return self.db.query(User).filter(User.role == role).count()

    def set_last_seen(self, user_id, seen_at: datetime) -> bool:
        """Stage a last-seen update; the service owns the transaction."""
        user = self.get_by_id(user_id, include_deleted=True)
        if not user:
            return False
        user.last_seen_at = seen_at
        return True

    def set_full_name(self, user_id, full_name: str) -> User | None:
        """Stage a full-name update; the service owns the transaction."""
        user = self.get_by_id(user_id, include_deleted=True)
        if not user:
            return None
        user.full_name = full_name
        return user

    @staticmethod
    def set_password_hash(user: User, password_hash: str) -> None:
        """Stage password and lockout-state changes on an existing user."""
        user.password_hash = password_hash
        user.failed_login_attempts = 0
        user.locked_until = None
    
    def get_by_employee_id(self, employee_id: str) -> User:
        """Get user by employee ID"""
        return self.db.query(User).filter(User.employee_id == employee_id).first()
    
    def disable_user(self, user_id) -> bool:
        """Disable user (soft delete)"""
        user = self.get_by_id(user_id, include_deleted=True)
        if user:
            user.is_active = False
            self.db.commit()
            logger.info(f"Disabled user: {user_id}")
            return True
        return False
    
    def enable_user(self, user_id) -> bool:
        """Enable user"""
        user = self.get_by_id(user_id, include_deleted=True)
        if user:
            user.is_active = True
            self.db.commit()
            logger.info(f"Enabled user: {user_id}")
            return True
        return False
