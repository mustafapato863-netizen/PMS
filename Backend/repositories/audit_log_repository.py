from sqlalchemy.orm import Session
from repositories.base_repository import BaseRepository
from models.models import AuditLog
import logging

logger = logging.getLogger(__name__)


class AuditLogRepository(BaseRepository[AuditLog]):
    """Repository for AuditLog model"""
    
    def get_by_table(self, table_name: str) -> list:
        """Get all audit logs for specific table"""
        return self.db.query(AuditLog).filter(AuditLog.table_name == table_name).all()
    
    def get_by_record(self, table_name: str, record_id) -> list:
        """Get all audit logs for specific record"""
        return self.db.query(AuditLog).filter(
            (AuditLog.table_name == table_name) &
            (AuditLog.record_id == record_id)
        ).order_by(AuditLog.performed_at.desc()).all()
    
    def get_by_operation(self, operation: str) -> list:
        """Get audit logs by operation type"""
        return self.db.query(AuditLog).filter(AuditLog.operation == operation).all()
    
    def get_by_user(self, user_id) -> list:
        """Get all audit logs created by user"""
        return self.db.query(AuditLog).filter(AuditLog.performed_by_user_id == user_id).all()
    
    def count_by_operation(self, operation: str) -> int:
        """Count audit logs by operation"""
        return self.db.query(AuditLog).filter(AuditLog.operation == operation).count()
    
    def count_by_table(self, table_name: str) -> int:
        """Count audit logs for table"""
        return self.db.query(AuditLog).filter(AuditLog.table_name == table_name).count()
    
    def get_recent(self, limit: int = 100) -> list:
        """Get recent audit logs"""
        return self.db.query(AuditLog).order_by(
            AuditLog.performed_at.desc()
        ).limit(limit).all()
