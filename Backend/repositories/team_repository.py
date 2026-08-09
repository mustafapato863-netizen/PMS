from sqlalchemy.orm import Session
from repositories.base_repository import BaseRepository
from models.models import Team
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class TeamRepository(BaseRepository[Team]):
    """Repository for Team model"""
    
    def get_by_name(
        self,
        name: str,
        include_deleted: bool = False,
        team_level: str = "employee",
    ) -> Team:
        """Get team by name"""
        query = self.db.query(Team).filter(Team.name == name, Team.team_level == team_level)
        if not include_deleted:
            query = query.filter(Team.is_active == True)
        return query.first()
    
    def get_by_db_name(
        self,
        db_name: str,
        include_deleted: bool = False,
        team_level: str = "employee",
    ) -> Team:
        """Get team by database name"""
        query = self.db.query(Team).filter(Team.db_name == db_name, Team.team_level == team_level)
        if not include_deleted:
            query = query.filter(Team.is_active == True)
        return query.first()
    
    def get_active_teams(self, team_level: str | None = None) -> list:
        """Get all active teams"""
        query = self.db.query(Team).filter(Team.is_active == True)
        if team_level:
            query = query.filter(Team.team_level == team_level)
        return query.all()
    
    def get_by_region(self, region: str, include_deleted: bool = False) -> list:
        """Get teams by region"""
        query = self.db.query(Team).filter(Team.region == region)
        if not include_deleted:
            query = query.filter(Team.is_active == True)
        return query.all()
    
    def count_active(self) -> int:
        """Count active teams"""
        return self.db.query(Team).filter(Team.is_active == True).count()
    
    def soft_delete(self, id: any) -> bool:
        """Soft delete (mark as inactive)"""
        team = self.get_by_id(id, include_deleted=True)
        if team:
            team.is_active = False
            team.updated_at = datetime.now()
            self.db.commit()
            logger.info(f"Soft deleted team: {id}")
            return True
        return False
    
    def restore(self, id: any) -> bool:
        """Restore soft-deleted team"""
        team = self.get_by_id(id, include_deleted=True)
        if team:
            team.is_active = True
            team.updated_at = datetime.now()
            self.db.commit()
            logger.info(f"Restored team: {id}")
            return True
        return False
