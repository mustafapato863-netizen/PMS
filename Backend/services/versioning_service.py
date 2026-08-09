"""Versioning Service
Manages historical snapshots and changes of PerformanceRecords.
"""

import uuid
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from models.models import PerformanceRecord, PerformanceRecordVersion

logger = logging.getLogger(__name__)


class VersioningService:
    """Enterprise service for versioning performance records"""

    @staticmethod
    def create_version(
        db: Session,
        record_id: str,
        year: int,
        changed_by_user_id: str = None,
        change_reason: str = None
    ) -> PerformanceRecordVersion:
        """
        Create a new version snapshot of a performance record.
        
        Args:
            db: Database session
            record_id: Record UUID
            year: Record partition year
            changed_by_user_id: User performing change
            change_reason: Reason for change
            
        Returns:
            PerformanceRecordVersion instance
        """
        try:
            rec_uuid = uuid.UUID(record_id) if isinstance(record_id, str) else record_id
            
            # Fetch original record
            record = db.query(PerformanceRecord).filter(
                PerformanceRecord.id == rec_uuid,
                PerformanceRecord.year == year
            ).first()
            
            if not record:
                raise ValueError(f"Performance record {record_id} for year {year} not found.")

            # Calculate next version number
            max_ver = db.query(func.max(PerformanceRecordVersion.version_number)).filter(
                PerformanceRecordVersion.original_record_id == rec_uuid
            ).scalar()
            
            next_version = (max_ver or 0) + 1

            # Convert user ID if string
            user_uuid = None
            if changed_by_user_id:
                user_uuid = uuid.UUID(changed_by_user_id) if isinstance(changed_by_user_id, str) else changed_by_user_id

            # Create version
            version = PerformanceRecordVersion(
                original_record_id=rec_uuid,
                original_record_year=year,
                version_number=next_version,
                score=record.score,
                grade=record.grade,
                status=record.status,
                changed_by_user_id=user_uuid,
                change_reason=change_reason
            )
            
            db.add(version)
            db.commit()
            db.refresh(version)
            
            logger.info(f"Created version {next_version} for performance record {record_id}")
            return version
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create version for record {record_id}: {e}")
            raise

    @staticmethod
    def get_version_history(db: Session, record_id: str) -> list:
        """
        Get all version snapshots for a record, newest first.
        """
        try:
            rec_uuid = uuid.UUID(record_id) if isinstance(record_id, str) else record_id
            return db.query(PerformanceRecordVersion).filter(
                PerformanceRecordVersion.original_record_id == rec_uuid
            ).order_by(PerformanceRecordVersion.version_number.desc()).all()
        except Exception as e:
            logger.error(f"Failed to query version history for record {record_id}: {e}")
            raise

    @staticmethod
    def get_record_as_of_date(
        db: Session,
        record_id: str,
        year: int,
        as_of: datetime
    ) -> dict:
        """
        Reconstruct a performance record's state as of a specific historical date.
        
        Args:
            db: Database session
            record_id: Record UUID
            year: Record partition year
            as_of: Historical timestamp
            
        Returns:
            Dict representing record state, or None
        """
        try:
            rec_uuid = uuid.UUID(record_id) if isinstance(record_id, str) else record_id
            
            # 1. Look for the latest version snapshot created <= as_of
            version = db.query(PerformanceRecordVersion).filter(
                PerformanceRecordVersion.original_record_id == rec_uuid,
                PerformanceRecordVersion.original_record_year == year,
                PerformanceRecordVersion.changed_at <= as_of
            ).order_by(PerformanceRecordVersion.version_number.desc()).first()

            if version:
                return {
                    "id": str(rec_uuid),
                    "year": year,
                    "score": version.score,
                    "grade": version.grade,
                    "status": version.status,
                    "version_number": version.version_number,
                    "as_of": as_of.isoformat()
                }

            # 2. If no version snapshot is found <= as_of, check the original record's uploaded_at.
            # If original uploaded_at <= as_of, then the record was in its initial state.
            record = db.query(PerformanceRecord).filter(
                PerformanceRecord.id == rec_uuid,
                PerformanceRecord.year == year
            ).first()

            if record and record.uploaded_at <= as_of:
                # Get the oldest version to reconstruct the initial state before any changes
                oldest_version = db.query(PerformanceRecordVersion).filter(
                    PerformanceRecordVersion.original_record_id == rec_uuid,
                    PerformanceRecordVersion.original_record_year == year
                ).order_by(PerformanceRecordVersion.version_number.asc()).first()

                if oldest_version:
                    return {
                        "id": str(rec_uuid),
                        "year": year,
                        "score": oldest_version.score,
                        "grade": oldest_version.grade,
                        "status": oldest_version.status,
                        "version_number": 0,  # Base version
                        "as_of": as_of.isoformat()
                    }
                else:
                    return {
                        "id": str(rec_uuid),
                        "year": year,
                        "score": record.score,
                        "grade": record.grade,
                        "status": record.status,
                        "version_number": 0,  # Base version
                        "as_of": as_of.isoformat()
                    }

            # Record did not exist yet as of this date
            return None

        except Exception as e:
            logger.error(f"Failed to get record {record_id} as of date: {e}")
            raise

    @staticmethod
    def diff_versions(v1: PerformanceRecordVersion, v2: PerformanceRecordVersion) -> dict:
        """
        Compare two versions and return a dictionary of differences.
        
        Returns:
            Dict: {field: {"old": val1, "new": val2}}
        """
        diff = {}
        fields = ["score", "grade", "status"]
        
        for field in fields:
            val1 = getattr(v1, field)
            val2 = getattr(v2, field)
            if val1 != val2:
                diff[field] = {
                    "old": float(val1) if hasattr(val1, "to_eng_string") or isinstance(val1, type(func.now())) else val1,
                    "new": float(val2) if hasattr(val2, "to_eng_string") or isinstance(val2, type(func.now())) else val2
                }
                
        return diff
