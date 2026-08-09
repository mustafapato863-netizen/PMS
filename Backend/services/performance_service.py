"""
Performance Service
Business logic for performance record management.
Handles performance queries, history tracking, and record operations.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from config.database import SessionLocal
from repositories.performance_repository import PerformanceRepository
from repositories.employee_repository import EmployeeRepository
from models.models import PerformanceRecord, KPIValue
import logging

logger = logging.getLogger(__name__)


class PerformanceService:
    """Service for managing performance records - Database-backed version."""

    @staticmethod
    def _record_to_dict(record, include_kpis: bool = False) -> Dict[str, Any]:
        record_dict = {
            'id': str(record.id),
            'employee_id': str(record.employee_id),
            'team_id': str(record.team_id),
            'month': record.month,
            'performance_level': record.performance_level,
            'position': record.position_name,
            'region': record.region,
            'year': record.year,
            'score': float(record.score),
            'grade': record.grade,
            'status': record.status,
            'uploaded_at': record.uploaded_at.isoformat() if record.uploaded_at else None,
        }
        if include_kpis:
            record_dict['kpi_values'] = [
                {
                    'kpi_key': kpi.kpi_key,
                    'actual_value': float(kpi.actual_value),
                    'target_value': float(kpi.target_value),
                    'achievement_ratio': min(max(float(kpi.achievement_ratio), 0.0), 1.0),
                    'weight_applied': float(kpi.weight_applied or 0),
                    'contribution': min(max(float(kpi.contribution or 0), 0.0), max(float(kpi.weight_applied or 0), 0.0)),
                    'cap_achievement': True,
                }
                for kpi in record.kpi_values
            ]
        return record_dict

    @staticmethod
    def get_monthly_records(team_id: any, month: str, year: int) -> List[Dict[str, Any]]:
        """
        Get all performance records for a team in a specific month.
        
        Args:
            team_id: Team ID
            month: Month name (January, February, etc.)
            year: Year
            
        Returns:
            List of performance record dicts
        """
        db = SessionLocal()
        try:
            repo = PerformanceRepository(db, PerformanceRecord)
            records = repo.get_monthly_records(team_id, month, year)
            
            return [PerformanceService._record_to_dict(record, include_kpis=True) for record in records]
        
        except Exception as e:
            logger.error(f"Failed to get monthly records for team {team_id}, month {month}, year {year}: {e}")
            raise
        
        finally:
            db.close()

    @staticmethod
    def get_employee_history(employee_id: any, year: int) -> List[Dict[str, Any]]:
        """
        Get all performance records for an employee in a specific year.
        
        Args:
            employee_id: Employee ID
            year: Year
            
        Returns:
            List of performance record dicts ordered by month
        """
        db = SessionLocal()
        try:
            repo = PerformanceRepository(db, PerformanceRecord)
            records = repo.get_employee_history(employee_id, year)
            
            return [PerformanceService._record_to_dict(record, include_kpis=True) for record in records]
        
        except Exception as e:
            logger.error(f"Failed to get employee history for {employee_id}, year {year}: {e}")
            raise
        
        finally:
            db.close()

    @staticmethod
    def get_by_grade(team_id: any, grade: str, month: str, year: int) -> List[Dict[str, Any]]:
        """
        Get all performance records for a team with a specific grade.
        
        Args:
            team_id: Team ID
            grade: Grade (A, B, C, D, E)
            month: Month name
            year: Year
            
        Returns:
            List of performance record dicts
        """
        db = SessionLocal()
        try:
            repo = PerformanceRepository(db, PerformanceRecord)
            records = repo.get_by_grade(team_id, grade, month, year)
            
            return [PerformanceService._record_to_dict(record) for record in records]
        
        except Exception as e:
            logger.error(f"Failed to get records by grade {grade}: {e}")
            raise
        
        finally:
            db.close()

    @staticmethod
    def get_by_status(team_id: any, status: str, month: str, year: int) -> List[Dict[str, Any]]:
        """
        Get all performance records for a team with a specific status.
        
        Args:
            team_id: Team ID
            status: Status (Exceeds, Meets, Below)
            month: Month name
            year: Year
            
        Returns:
            List of performance record dicts
        """
        db = SessionLocal()
        try:
            repo = PerformanceRepository(db, PerformanceRecord)
            records = repo.get_by_status(team_id, status, month, year)
            
            result = []
            for record in records:
                record_dict = {
                    'id': str(record.id),
                    'employee_id': str(record.employee_id),
                    'team_id': str(record.team_id),
                    'month': record.month,
                    'year': record.year,
                    'score': float(record.score),
                    'grade': record.grade,
                    'status': record.status,
                    'uploaded_at': record.uploaded_at.isoformat() if record.uploaded_at else None,
                }
                result.append(record_dict)
            
            return result
        
        except Exception as e:
            logger.error(f"Failed to get records by status {status}: {e}")
            raise
        
        finally:
            db.close()

    @staticmethod
    def create_performance_record(
        employee_id: any,
        team_id: any,
        month: str,
        year: int,
        score: float,
        grade: str,
        status: str,
        performance_level: str = "Employee",
        kpi_data: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[bool, Dict[str, Any], List[str]]:
        """
        Create a new performance record with KPI values.
        
        Args:
            employee_id: Employee ID
            team_id: Team ID
            month: Month name
            year: Year
            score: Performance score
            grade: Grade (A, B, C, D, E)
            status: Status (Exceeds, Meets, Below)
            kpi_data: Optional list of KPI value dicts
            
        Returns:
            Tuple (success, record_dict, errors)
        """
        errors = []
        
        db = SessionLocal()
        try:
            repo = PerformanceRepository(db, PerformanceRecord)
            
            # Check if record already exists
            existing = repo.get_by_employee_month(employee_id, month, year)
            if existing:
                errors.append(f"Performance record already exists for {month} {year}")
                return False, {}, errors
            
            # Create record
            record_data = {
                'employee_id': employee_id,
                'team_id': team_id,
                'month': month,
                'year': year,
                'score': score,
                'grade': grade,
                'status': status,
                'performance_level': performance_level,
            }
            
            record = repo.create(record_data)
            logger.info(f"Created performance record: {record.id}")
            
            # Add KPI values
            if kpi_data:
                for kpi in kpi_data:
                    kpi_value = KPIValue(
                        record_id=record.id,
                        record_year=year,
                        kpi_key=kpi['kpi_key'],
                        actual_value=kpi['actual_value'],
                        target_value=kpi['target_value'],
                        achievement_ratio=kpi.get('achievement_ratio', 0),
                        weight_applied=kpi.get('weight_applied', 0),
                        contribution=kpi.get('contribution', 0),
                    )
                    db.add(kpi_value)
            
            db.commit()
            
            record_dict = PerformanceService._record_to_dict(record)
            
            return True, record_dict, errors
        
        except Exception as e:
            errors.append(f"Failed to create performance record: {str(e)}")
            logger.error(f"Create performance record error: {e}")
            db.rollback()
            return False, {}, errors
        
        finally:
            db.close()

    @staticmethod
    def update_performance_record(
        record_id: any,
        year: int,
        **updates
    ) -> Tuple[bool, Dict[str, Any], List[str]]:
        """
        Update a performance record.
        
        Args:
            record_id: Record ID
            year: Year (for composite key)
            **updates: Fields to update (score, grade, status, etc.)
            
        Returns:
            Tuple (success, updated_record_dict, errors)
        """
        errors = []
        
        db = SessionLocal()
        try:
            repo = PerformanceRepository(db, PerformanceRecord)
            record = repo.get_by_id(record_id)
            
            if not record:
                errors.append(f"Performance record not found")
                return False, {}, errors
            
            # Update fields
            update_data = {}
            for key in ['score', 'grade', 'status']:
                if key in updates:
                    update_data[key] = updates[key]
            
            if update_data:
                updated_record = repo.update(record_id, update_data)
            else:
                updated_record = record
            
            db.commit()
            logger.info(f"Updated performance record: {record_id}")
            
            record_dict = PerformanceService._record_to_dict(updated_record)
            
            return True, record_dict, errors
        
        except Exception as e:
            errors.append(f"Failed to update performance record: {str(e)}")
            logger.error(f"Update performance record error: {e}")
            db.rollback()
            return False, {}, errors
        
        finally:
            db.close()

    @staticmethod
    def delete_performance_record(record_id: any, year: int) -> Tuple[bool, List[str]]:
        """
        Delete a performance record.
        
        Args:
            record_id: Record ID
            year: Year (for composite key)
            
        Returns:
            Tuple (success, errors)
        """
        errors = []
        
        db = SessionLocal()
        try:
            repo = PerformanceRepository(db, PerformanceRecord)
            record = repo.get_by_id(record_id)
            
            if not record:
                errors.append(f"Performance record not found")
                return False, errors
            
            success = repo.delete(record_id)
            
            if success:
                logger.info(f"Deleted performance record: {record_id}")
                # KPI values are deleted automatically due to CASCADE
                db.commit()
                return True, errors
            else:
                errors.append("Failed to delete performance record")
                return False, errors
        
        except Exception as e:
            errors.append(f"Failed to delete performance record: {str(e)}")
            logger.error(f"Delete performance record error: {e}")
            db.rollback()
            return False, errors
        
        finally:
            db.close()

    @staticmethod
    def get_team_yearly_records(team_id: any, year: int) -> List[Dict[str, Any]]:
        """
        Get all performance records for a team in a specific year.
        
        Args:
            team_id: Team ID
            year: Year
            
        Returns:
            List of performance record dicts
        """
        db = SessionLocal()
        try:
            repo = PerformanceRepository(db, PerformanceRecord)
            records = repo.get_team_yearly_records(team_id, year)
            
            return [PerformanceService._record_to_dict(record) for record in records]
        
        except Exception as e:
            logger.error(f"Failed to get team yearly records for team {team_id}, year {year}: {e}")
            raise
        
        finally:
            db.close()

    @staticmethod
    def count_by_grade(team_id: any, grade: str, month: str, year: int) -> int:
        """
        Count performance records by grade.
        
        Args:
            team_id: Team ID
            grade: Grade
            month: Month
            year: Year
            
        Returns:
            Count of records
        """
        db = SessionLocal()
        try:
            repo = PerformanceRepository(db, PerformanceRecord)
            return repo.count_by_grade(team_id, grade, month, year)
        
        except Exception as e:
            logger.error(f"Failed to count records by grade: {e}")
            raise
        
        finally:
            db.close()
