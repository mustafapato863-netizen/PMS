"""
Employee Service
Business logic for employee management.
Handles employee queries, team relationships, and employee operations.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from config.database import SessionLocal
from repositories.employee_repository import EmployeeRepository
from repositories.team_repository import TeamRepository
from models.models import Employee, Team
import logging
import uuid

logger = logging.getLogger(__name__)


class EmployeeService:
    """Service for managing employees - Database-backed version."""

    @staticmethod
    def _resolve_employee(repo: EmployeeRepository, identifier: str, include_deleted: bool = False) -> Employee | None:
        """Resolve either the external employee ID used by the UI or the internal UUID."""
        employee = repo.get_by_employee_id(identifier, include_deleted=include_deleted)
        if employee:
            return employee
        try:
            return repo.get_by_id(uuid.UUID(str(identifier)), include_deleted=include_deleted)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def get_all_employees(include_deleted: bool = False) -> List[Dict[str, Any]]:
        """
        Get all employees from database.
        
        Returns:
            List of employee dicts
        """
        db = SessionLocal()
        try:
            repo = EmployeeRepository(db, Employee)
            employees = repo.get_all(include_deleted=include_deleted)
            
            result = []
            for emp in employees:
                emp_dict = {
                    'id': str(emp.id),
                    'employee_id': emp.employee_id,
                    'name': emp.name,
                    'team_id': str(emp.team_id),
                    'region': emp.region,
                    'position': emp.position_name,
                    'is_active': emp.is_active,
                    'created_at': emp.created_at.isoformat() if emp.created_at else None,
                    'updated_at': emp.updated_at.isoformat() if emp.updated_at else None,
                }
                
                # Add team name
                if emp.team:
                    emp_dict['team_name'] = emp.team.name
                
                result.append(emp_dict)
            
            return result
        
        except Exception as e:
            logger.error(f"Failed to get all employees: {e}")
            raise
        
        finally:
            db.close()

    @staticmethod
    def get_employee(employee_id_or_uuid: str, include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get single employee by UUID or employee_id.
        
        Args:
            employee_id_or_uuid: Employee UUID or employee_id
            
        Returns:
            Employee dict or None
        """
        db = SessionLocal()
        try:
            repo = EmployeeRepository(db, Employee)
            
            # Try as UUID first
            try:
                emp = repo.get_by_id(employee_id_or_uuid, include_deleted=include_deleted)
            except:
                emp = None
            
            # Try as employee_id
            if not emp:
                emp = repo.get_by_employee_id(employee_id_or_uuid, include_deleted=include_deleted)
            
            if not emp:
                return None
            
            emp_dict = {
                'id': str(emp.id),
                'employee_id': emp.employee_id,
                'name': emp.name,
                'team_id': str(emp.team_id),
                'region': emp.region,
                'position': emp.position_name,
                'is_active': emp.is_active,
                'created_at': emp.created_at.isoformat() if emp.created_at else None,
                'updated_at': emp.updated_at.isoformat() if emp.updated_at else None,
            }
            
            # Add team name
            if emp.team:
                emp_dict['team_name'] = emp.team.name
            
            return emp_dict
        
        except Exception as e:
            logger.error(f"Failed to get employee {employee_id_or_uuid}: {e}")
            raise
        
        finally:
            db.close()

    @staticmethod
    def get_employees_by_team(team_id: any, include_deleted: bool = False) -> List[Dict[str, Any]]:
        """
        Get all employees in a team.
        
        Args:
            team_id: Team ID
            
        Returns:
            List of employee dicts
        """
        db = SessionLocal()
        try:
            repo = EmployeeRepository(db, Employee)
            employees = repo.get_by_team(team_id, include_deleted=include_deleted)
            
            result = []
            for emp in employees:
                emp_dict = {
                    'id': str(emp.id),
                    'employee_id': emp.employee_id,
                    'name': emp.name,
                    'team_id': str(emp.team_id),
                    'region': emp.region,
                    'position': emp.position_name,
                    'is_active': emp.is_active,
                    'created_at': emp.created_at.isoformat() if emp.created_at else None,
                    'updated_at': emp.updated_at.isoformat() if emp.updated_at else None,
                }
                
                if emp.team:
                    emp_dict['team_name'] = emp.team.name
                
                result.append(emp_dict)
            
            return result
        
        except Exception as e:
            logger.error(f"Failed to get employees for team {team_id}: {e}")
            raise
        
        finally:
            db.close()

    @staticmethod
    def get_active_employees_by_team(team_id: any) -> List[Dict[str, Any]]:
        """
        Get all active employees in a team.
        
        Args:
            team_id: Team ID
            
        Returns:
            List of active employee dicts
        """
        db = SessionLocal()
        try:
            repo = EmployeeRepository(db, Employee)
            employees = repo.get_active_by_team(team_id)
            
            result = []
            for emp in employees:
                emp_dict = {
                    'id': str(emp.id),
                    'employee_id': emp.employee_id,
                    'name': emp.name,
                    'team_id': str(emp.team_id),
                    'region': emp.region,
                    'position': emp.position_name,
                    'is_active': emp.is_active,
                    'created_at': emp.created_at.isoformat() if emp.created_at else None,
                    'updated_at': emp.updated_at.isoformat() if emp.updated_at else None,
                }
                
                if emp.team:
                    emp_dict['team_name'] = emp.team.name
                
                result.append(emp_dict)
            
            return result
        
        except Exception as e:
            logger.error(f"Failed to get active employees for team {team_id}: {e}")
            raise
        
        finally:
            db.close()

    @staticmethod
    def search_employees(name: str, include_deleted: bool = False) -> List[Dict[str, Any]]:
        """
        Search employees by name (case insensitive).
        
        Args:
            name: Name to search for
            
        Returns:
            List of matching employee dicts
        """
        db = SessionLocal()
        try:
            repo = EmployeeRepository(db, Employee)
            employees = repo.search_by_name(name, include_deleted=include_deleted)
            
            result = []
            for emp in employees:
                emp_dict = {
                    'id': str(emp.id),
                    'employee_id': emp.employee_id,
                    'name': emp.name,
                    'team_id': str(emp.team_id),
                    'region': emp.region,
                    'position': emp.position_name,
                    'is_active': emp.is_active,
                    'created_at': emp.created_at.isoformat() if emp.created_at else None,
                    'updated_at': emp.updated_at.isoformat() if emp.updated_at else None,
                }
                
                if emp.team:
                    emp_dict['team_name'] = emp.team.name
                
                result.append(emp_dict)
            
            return result
        
        except Exception as e:
            logger.error(f"Failed to search employees with name '{name}': {e}")
            raise
        
        finally:
            db.close()

    @staticmethod
    def create_employee(
        employee_id: str,
        name: str,
        team_id: any,
        region: str = "UAE"
    ) -> Tuple[bool, Dict[str, Any], List[str]]:
        """
        Create a new employee.
        
        Args:
            employee_id: External employee ID
            name: Employee name
            team_id: Team ID
            region: Region (default: UAE)
            
        Returns:
            Tuple (success, employee_dict, errors)
        """
        errors = []
        
        db = SessionLocal()
        try:
            repo = EmployeeRepository(db, Employee)
            
            # Check if employee already exists
            existing = repo.get_by_employee_id(employee_id)
            if existing:
                errors.append(f"Employee with ID '{employee_id}' already exists")
                return False, {}, errors
            
            # Verify team exists
            team_repo = TeamRepository(db, Team)
            team = team_repo.get_by_id(team_id)
            if not team:
                errors.append(f"Team '{team_id}' not found")
                return False, {}, errors
            
            # Create employee
            emp_data = {
                'id': uuid.uuid4(),
                'employee_id': employee_id,
                'name': name,
                'team_id': team_id,
                'region': region,
                'is_active': True,
            }
            
            emp = repo.create(emp_data)
            db.commit()
            logger.info(f"Created employee: {employee_id}")
            
            emp_dict = {
                'id': str(emp.id),
                'employee_id': emp.employee_id,
                'name': emp.name,
                'team_id': str(emp.team_id),
                'region': emp.region,
                'position': emp.position_name,
                'is_active': emp.is_active,
                'team_name': team.name,
            }
            
            return True, emp_dict, errors
        
        except Exception as e:
            errors.append(f"Failed to create employee: {str(e)}")
            logger.error(f"Create employee error: {e}")
            db.rollback()
            return False, {}, errors
        
        finally:
            db.close()

    @staticmethod
    def update_employee(
        employee_uuid: any,
        **updates
    ) -> Tuple[bool, Dict[str, Any], List[str]]:
        """
        Update an employee.
        
        Args:
            employee_uuid: Employee UUID
            **updates: Fields to update (name, team_id, region, is_active, etc.)
            
        Returns:
            Tuple (success, updated_employee_dict, errors)
        """
        errors = []
        
        db = SessionLocal()
        try:
            repo = EmployeeRepository(db, Employee)
            emp = repo.get_by_id(employee_uuid)
            
            if not emp:
                errors.append(f"Employee not found")
                return False, {}, errors
            
            # Update fields
            update_data = {}
            for key in ['name', 'team_id', 'region', 'is_active']:
                if key in updates:
                    update_data[key] = updates[key]
            
            # If team_id is changing, verify new team exists
            if 'team_id' in update_data:
                team_repo = TeamRepository(db, Team)
                team = team_repo.get_by_id(update_data['team_id'])
                if not team:
                    errors.append(f"Team '{update_data['team_id']}' not found")
                    return False, {}, errors
            
            if update_data:
                updated_emp = repo.update(employee_uuid, update_data)
            else:
                updated_emp = emp
            
            db.commit()
            logger.info(f"Updated employee: {employee_uuid}")
            
            # Reload team info
            team_name = updated_emp.team.name if updated_emp.team else None
            
            emp_dict = {
                'id': str(updated_emp.id),
                'employee_id': updated_emp.employee_id,
                'name': updated_emp.name,
                'team_id': str(updated_emp.team_id),
                'region': updated_emp.region,
                'is_active': updated_emp.is_active,
                'created_at': updated_emp.created_at.isoformat() if updated_emp.created_at else None,
                'updated_at': updated_emp.updated_at.isoformat() if updated_emp.updated_at else None,
            }
            
            if team_name:
                emp_dict['team_name'] = team_name
            
            return True, emp_dict, errors
        
        except Exception as e:
            errors.append(f"Failed to update employee: {str(e)}")
            logger.error(f"Update employee error: {e}")
            db.rollback()
            return False, {}, errors
        
        finally:
            db.close()

    @staticmethod
    def update_employee_assignment(
        employee_identifier: str,
        team_name: str,
        performance_level: str,
    ) -> Tuple[bool, Dict[str, Any], List[str]]:
        """Update an active employee's team and performance level atomically."""
        from utils.performance_levels import normalize_performance_level

        errors: List[str] = []
        db = SessionLocal()
        try:
            employee_repo = EmployeeRepository(db, Employee)
            team_repo = TeamRepository(db, Team)
            employee = EmployeeService._resolve_employee(employee_repo, employee_identifier)
            if not employee:
                return False, {}, ["Employee not found"]

            team = team_repo.get_by_name(team_name) or team_repo.get_by_db_name(team_name)
            if not team:
                return False, {}, [f"Team '{team_name}' not found"]

            try:
                level = normalize_performance_level(performance_level, allow_all=False)
            except ValueError as exc:
                return False, {}, [str(exc)]

            employee.team_id = team.id
            employee.performance_level = level
            db.commit()
            db.refresh(employee)
            return True, {
                "employee_id": employee.employee_id,
                "team": team.name,
                "performance_level": employee.performance_level,
            }, errors
        except Exception as exc:
            db.rollback()
            logger.error("Update employee assignment failed: %s", exc)
            return False, {}, [f"Failed to update employee assignment: {exc}"]
        finally:
            db.close()

    @staticmethod
    def delete_employee(employee_uuid: any, performed_by_user_id: str = None) -> Tuple[bool, List[str]]:
        """
        Delete an employee (soft delete - mark as inactive).
        
        Args:
            employee_uuid: Employee UUID
            performed_by_user_id: ID of the user performing the action
            
        Returns:
            Tuple (success, errors)
        """
        errors = []
        db = SessionLocal()
        try:
            from services.soft_delete_service import SoftDeleteService
            repo = EmployeeRepository(db, Employee)
            employee = EmployeeService._resolve_employee(repo, str(employee_uuid))
            if not employee:
                return False, ["Employee not found or already inactive"]
            success = SoftDeleteService.soft_delete_employee(db, employee.id, performed_by_user_id)
            if not success:
                errors.append("Employee not found or already inactive")
                return False, errors
            return True, errors
        except Exception as e:
            errors.append(f"Failed to delete employee: {str(e)}")
            logger.error(f"Delete employee error: {e}")
            return False, errors
        finally:
            db.close()

    @staticmethod
    def restore_employee(employee_uuid: any, performed_by_user_id: str = None) -> Tuple[bool, List[str]]:
        """
        Restore a soft-deleted employee.
        
        Args:
            employee_uuid: Employee UUID
            performed_by_user_id: ID of the user performing the action
            
        Returns:
            Tuple (success, errors)
        """
        errors = []
        db = SessionLocal()
        try:
            from services.soft_delete_service import SoftDeleteService
            success = SoftDeleteService.restore_employee(db, employee_uuid, performed_by_user_id)
            if not success:
                errors.append("Employee not found or already active")
                return False, errors
            return True, errors
        except Exception as e:
            errors.append(f"Failed to restore employee: {str(e)}")
            logger.error(f"Restore employee error: {e}")
            return False, errors
        finally:
            db.close()

    @staticmethod
    def count_employees_by_team(team_id: any) -> int:
        """
        Count employees in a team.
        
        Args:
            team_id: Team ID
            
        Returns:
            Count of employees
        """
        db = SessionLocal()
        try:
            repo = EmployeeRepository(db, Employee)
            return repo.count_by_team(team_id)
        
        except Exception as e:
            logger.error(f"Failed to count employees for team {team_id}: {e}")
            raise
        
        finally:
            db.close()

    @staticmethod
    def get_active_employee_count() -> int:
        """
        Get total count of active employees.
        
        Returns:
            Count of active employees
        """
        db = SessionLocal()
        try:
            repo = EmployeeRepository(db, Employee)
            return repo.count_active()
        
        except Exception as e:
            logger.error(f"Failed to count active employees: {e}")
            raise
        
        finally:
            db.close()

    @staticmethod
    def get_employees_by_region(region: str) -> List[Dict[str, Any]]:
        """
        Get all employees in a specific region.
        
        Args:
            region: Region code (e.g., 'UAE')
            
        Returns:
            List of employee dicts
        """
        db = SessionLocal()
        try:
            repo = EmployeeRepository(db, Employee)
            employees = repo.get_by_region(region)
            
            result = []
            for emp in employees:
                emp_dict = {
                    'id': str(emp.id),
                    'employee_id': emp.employee_id,
                    'name': emp.name,
                    'team_id': str(emp.team_id),
                    'region': emp.region,
                    'position': emp.position_name,
                    'is_active': emp.is_active,
                    'created_at': emp.created_at.isoformat() if emp.created_at else None,
                    'updated_at': emp.updated_at.isoformat() if emp.updated_at else None,
                }
                
                if emp.team:
                    emp_dict['team_name'] = emp.team.name
                
                result.append(emp_dict)
            
            return result
        
        except Exception as e:
            logger.error(f"Failed to get employees by region '{region}': {e}")
            raise
        
        finally:
            db.close()
