"""Soft Delete Service
Manages soft delete and restore operations across models and records.
"""

import uuid
import logging
from sqlalchemy.orm import Session
from services.audit_service import AuditService
from models.models import Employee, Team, User, Action

logger = logging.getLogger(__name__)


class SoftDeleteService:
    """Handles soft delete and restore operations across main entity models"""

    @staticmethod
    def soft_delete_employee(db: Session, employee_id: str, performed_by_user_id: str = None) -> bool:
        """Soft delete an employee by setting is_active = False"""
        try:
            emp_uuid = uuid.UUID(employee_id) if isinstance(employee_id, str) else employee_id
            emp = db.query(Employee).filter(Employee.id == emp_uuid).first()
            if not emp or not emp.is_active:
                return False

            old_values = {"is_active": True}
            emp.is_active = False
            new_values = {"is_active": False}
            db.commit()

            # Log to audit trail
            AuditService.log_operation(
                db=db,
                table_name="employees",
                operation="SOFT_DELETE",
                record_id=str(emp.id),
                old_values=old_values,
                new_values=new_values,
                performed_by_user_id=performed_by_user_id
            )
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to soft delete employee {employee_id}: {e}")
            return False

    @staticmethod
    def restore_employee(db: Session, employee_id: str, performed_by_user_id: str = None) -> bool:
        """Restore a soft-deleted employee by setting is_active = True"""
        try:
            emp_uuid = uuid.UUID(employee_id) if isinstance(employee_id, str) else employee_id
            emp = db.query(Employee).filter(Employee.id == emp_uuid).first()
            if not emp or emp.is_active:
                return False

            old_values = {"is_active": False}
            emp.is_active = True
            new_values = {"is_active": True}
            db.commit()

            # Log to audit trail
            AuditService.log_operation(
                db=db,
                table_name="employees",
                operation="RESTORE",
                record_id=str(emp.id),
                old_values=old_values,
                new_values=new_values,
                performed_by_user_id=performed_by_user_id
            )
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to restore employee {employee_id}: {e}")
            return False

    @staticmethod
    def soft_delete_record(db: Session, model_class, record_id: str, table_name: str, performed_by_user_id: str = None) -> bool:
        """Generic helper to soft delete Team, User, or Action models"""
        try:
            rec_uuid = uuid.UUID(record_id) if isinstance(record_id, str) else record_id
            record = db.query(model_class).filter(model_class.id == rec_uuid).first()
            if not record or not getattr(record, "is_active", True):
                return False

            old_values = {"is_active": True}
            record.is_active = False
            new_values = {"is_active": False}
            db.commit()

            # Log to audit trail
            AuditService.log_operation(
                db=db,
                table_name=table_name,
                operation="SOFT_DELETE",
                record_id=str(record.id),
                old_values=old_values,
                new_values=new_values,
                performed_by_user_id=performed_by_user_id
            )
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to soft delete {table_name} record {record_id}: {e}")
            return False

    @staticmethod
    def restore_record(db: Session, model_class, record_id: str, table_name: str, performed_by_user_id: str = None) -> bool:
        """Generic helper to restore Team, User, or Action models"""
        try:
            rec_uuid = uuid.UUID(record_id) if isinstance(record_id, str) else record_id
            record = db.query(model_class).filter(model_class.id == rec_uuid).first()
            if not record or getattr(record, "is_active", False):
                return False

            old_values = {"is_active": False}
            record.is_active = True
            new_values = {"is_active": True}
            db.commit()

            # Log to audit trail
            AuditService.log_operation(
                db=db,
                table_name=table_name,
                operation="RESTORE",
                record_id=str(record.id),
                old_values=old_values,
                new_values=new_values,
                performed_by_user_id=performed_by_user_id
            )
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to restore {table_name} record {record_id}: {e}")
            return False
