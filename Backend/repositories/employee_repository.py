from sqlalchemy.orm import Session
from repositories.base_repository import BaseRepository
from models.models import Employee
import logging

logger = logging.getLogger(__name__)


class EmployeeRepository(BaseRepository[Employee]):
    """Repository for Employee model"""
    
    def get_by_employee_id(self, employee_id: str, include_deleted: bool = False) -> Employee:
        """Get employee by external employee ID"""
        query = self.db.query(Employee).filter(Employee.employee_id == employee_id)
        if not include_deleted:
            query = query.filter(Employee.is_active == True)
        return query.first()
    
    def get_by_team(self, team_id, include_deleted: bool = False) -> list:
        """Get all employees in team"""
        query = self.db.query(Employee).filter(Employee.team_id == team_id)
        if not include_deleted:
            query = query.filter(Employee.is_active == True)
        return query.all()
    
    def get_active_by_team(self, team_id) -> list:
        """Get active employees in team"""
        return self.get_by_team(team_id, include_deleted=False)
    
    def count_by_team(self, team_id, include_deleted: bool = False) -> int:
        """Count employees in team"""
        query = self.db.query(Employee).filter(Employee.team_id == team_id)
        if not include_deleted:
            query = query.filter(Employee.is_active == True)
        return query.count()
    
    def get_by_region(self, region: str, include_deleted: bool = False) -> list:
        """Get employees by region"""
        query = self.db.query(Employee).filter(Employee.region == region)
        if not include_deleted:
            query = query.filter(Employee.is_active == True)
        return query.all()
    
    def count_active(self) -> int:
        """Count all active employees"""
        return self.db.query(Employee).filter(Employee.is_active == True).count()
    
    def search_by_name(self, name: str, include_deleted: bool = False) -> list:
        """Search employees by name (case insensitive)"""
        query = self.db.query(Employee).filter(
            Employee.name.ilike(f"%{name}%")
        )
        if not include_deleted:
            query = query.filter(Employee.is_active == True)
        return query.all()
