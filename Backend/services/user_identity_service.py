from sqlalchemy.orm import Session

from models.models import Employee, User
from utils.user_identity import humanize_username


class UserIdentityService:
    """Resolve the user-facing identity without changing login credentials."""

    @staticmethod
    def display_name(db: Session, user: User) -> str:
        if user.full_name and user.full_name.strip():
            return user.full_name.strip()

        if user.employee_id:
            employee_name = (
                db.query(Employee.name)
                .filter(Employee.employee_id == user.employee_id)
                .scalar()
            )
            if employee_name and employee_name.strip():
                return employee_name.strip()

        return humanize_username(user.username)
