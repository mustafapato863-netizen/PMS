"""Audit Logging Service
Provides enterprise change-tracking and history query capabilities.
"""

import csv
import io
import json
import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from models.models import AuditLog

logger = logging.getLogger(__name__)


class AuditService:
    """Enterprise Audit Log Service"""

    @staticmethod
    def log_operation(
        db: Session,
        table_name: str,
        operation: str,
        record_id: str,
        old_values: Optional[dict] = None,
        new_values: Optional[dict] = None,
        performed_by_user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> AuditLog:
        """
        Record a data modification operation to the audit log table.
        """
        try:
            # Convert string IDs to UUIDs if appropriate
            u_record_id = uuid.UUID(record_id) if isinstance(record_id, str) else record_id
            u_user_id = uuid.UUID(performed_by_user_id) if isinstance(performed_by_user_id, str) else performed_by_user_id
            
            audit = AuditLog(
                id=uuid.uuid4(),
                table_name=table_name,
                operation=operation,
                record_id=u_record_id,
                old_values=old_values,
                new_values=new_values,
                performed_by_user_id=u_user_id,
                ip_address=ip_address,
                request_id=request_id
            )
            db.add(audit)
            db.commit()
            db.refresh(audit)
            return audit
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to save audit log entry: {e}")
            raise

    @staticmethod
    def get_record_history(
        db: Session,
        table_name: str,
        record_id: str
    ) -> List[AuditLog]:
        """
        Retrieve history of modifications for a specific record, ordered reverse-chronologically.
        """
        try:
            u_record_id = uuid.UUID(record_id) if isinstance(record_id, str) else record_id
        except ValueError:
            return []
            
        return (
            db.query(AuditLog)
            .filter(
                AuditLog.table_name == table_name,
                AuditLog.record_id == u_record_id
            )
            .order_by(AuditLog.performed_at.desc())
            .all()
        )

    @staticmethod
    def export_audit_logs(
        db: Session,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        table_name: Optional[str] = None
    ) -> str:
        """
        Export matching audit logs within a date range as a CSV string.
        """
        query = db.query(AuditLog)
        
        if start_date:
            query = query.filter(AuditLog.performed_at >= start_date)
        if end_date:
            query = query.filter(AuditLog.performed_at <= end_date)
        if table_name:
            query = query.filter(AuditLog.table_name == table_name)
            
        logs = query.order_by(AuditLog.performed_at.desc()).all()
        
        # Build CSV output
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "id", "table_name", "operation", "record_id", 
            "old_values", "new_values", "performed_by_user_id", 
            "performed_at", "ip_address", "request_id"
        ])
        
        for log in logs:
            writer.writerow([
                str(log.id),
                log.table_name,
                log.operation,
                str(log.record_id) if log.record_id else "",
                json.dumps(log.old_values) if log.old_values else "",
                json.dumps(log.new_values) if log.new_values else "",
                str(log.performed_by_user_id) if log.performed_by_user_id else "",
                log.performed_at.isoformat() if log.performed_at else "",
                log.ip_address or "",
                log.request_id or ""
            ])
            
        return output.getvalue()
