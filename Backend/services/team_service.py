"""
Team Service
Business logic for team management.
Handles team creation, validation, and configuration.
"""

import uuid
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from config.database import SessionLocal
from config.loader import (
    ConfigurationError,
    find_team_config_by_db_name,
    iter_employee_kpi_configs,
    load_team_config,
)
from repositories.team_repository import TeamRepository
from models.models import Team, TeamKPIConfig
from models.team_models import TeamCreateRequest, TeamUpdateRequest
from data_cleaning import CleanerFactory
import logging

logger = logging.getLogger(__name__)


class TeamService:
    """Service for managing teams - Database-backed version."""

    @staticmethod
    def _load_team_config(team_name: str, db_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Resolve a team config by team name first, then db_name."""
        try:
            return load_team_config(team_name)
        except ConfigurationError:
            if db_name:
                return find_team_config_by_db_name(db_name)
        return None

    @staticmethod
    def _build_team_payload(team: Team, db: Session) -> Dict[str, Any]:
        """Build a response payload using config JSON as the source of truth when available."""
        config = TeamService._load_team_config(team.name, team.db_name)

        kpi_configs = db.query(TeamKPIConfig).filter(
            TeamKPIConfig.team_id == team.id,
            TeamKPIConfig.performance_level == "Employee",
        ).all()
        if kpi_configs:
            kpi_keys = [kpi.kpi_key for kpi in kpi_configs]
            kpi_weights = {kpi.kpi_key: float(kpi.weight) for kpi in kpi_configs}
        elif config:
            kpi_keys = [kpi["key"] for kpi in config.get("kpis", [])]
            kpi_weights = {kpi["key"]: float(kpi["weight"]) for kpi in config.get("kpis", [])}
        else:
            kpi_keys = []
            kpi_weights = {}

        return {
            "id": str(team.id),
            "name": team.name,
            "display_name": (
                config.get("team", team.display_name or team.name)
                if config
                else (team.display_name or team.name)
            ),
            "db_name": team.db_name,
            "team_level": team.team_level,
            "region": config.get("region", team.region) if config else team.region,
            "description": None,
            "kpi_keys": kpi_keys,
            "kpi_weights": kpi_weights,
            "data_source": "Excel" if config else "Database",
            "team_lead": None,
            "team_lead_email": None,
            "is_active": team.is_active,
            "created_at": team.created_at.isoformat() if team.created_at else None,
            "updated_at": team.updated_at.isoformat() if team.updated_at else None,
        }

    @staticmethod
    def get_all_teams() -> List[Dict[str, Any]]:
        """
        Get all team configurations from database.
        
        Returns:
            List of team dicts
        """
        db = SessionLocal()
        try:
            repo = TeamRepository(db, Team)
            teams = repo.get_active_teams(team_level="employee")
            
            result = []
            for team in teams:
                team_dict = TeamService._build_team_payload(team, db)

                # Add cleaner availability
                try:
                    available_cleaners = CleanerFactory.get_available_teams()
                    team_dict['has_cleaner'] = team.name in available_cleaners or team.db_name in available_cleaners
                except Exception as e:
                    logger.warning(f"Could not load cleaner info: {e}")
                    team_dict['has_cleaner'] = False
                
                result.append(team_dict)
            
            return result
        
        except Exception as e:
            logger.error(f"Failed to get all teams: {e}")
            raise
        
        finally:
            db.close()

    @staticmethod
    def get_team(team_name: str) -> Optional[Dict[str, Any]]:
        """
        Get single team from database.
        
        Args:
            team_name: Team name
            
        Returns:
            Team dict or None
        """
        db = SessionLocal()
        try:
            repo = TeamRepository(db, Team)
            team = repo.get_by_name(team_name)
            
            if not team:
                return None

            return TeamService._build_team_payload(team, db)
        
        except Exception as e:
            logger.error(f"Failed to get team {team_name}: {e}")
            raise
        
        finally:
            db.close()

    @staticmethod
    def create_team(request: TeamCreateRequest) -> Tuple[bool, Dict[str, Any], List[str]]:
        """
        Create new team in database.
        
        Args:
            request: Team creation request
            
        Returns:
            Tuple (success, team_dict, errors)
        """
        errors = []
        team_name = request.name.lower().replace(' ', '_')
        
        db = SessionLocal()
        try:
            repo = TeamRepository(db, Team)
            
            # Validate team doesn't exist
            existing_team = repo.get_by_name(team_name)
            if existing_team:
                errors.append(f"Team '{team_name}' already exists")
                return False, {}, errors
            
            # Validate team name format
            if not TeamService._is_valid_team_name(team_name):
                errors.append("Team name must contain only letters, numbers, and underscores")
                return False, {}, errors
            
            config = TeamService._load_team_config(request.name, request.db_name)

            # Create team
            team_name_value = config.get('team', request.name) if config else team_name
            db_name_value = config.get('db_name', request.db_name or team_name) if config else (request.db_name or team_name)
            region_value = config.get('region', request.region or 'UAE') if config else (request.region or 'UAE')

            team_data = {
                'id': uuid.uuid4(),
                'name': team_name_value,
                'db_name': db_name_value,
                'display_name': config.get('team', request.display_name) if config else request.display_name,
                'region': region_value,
                'team_level': 'employee',
                'is_active': True,
            }
            
            team = repo.create(team_data)
            logger.info(f"Created team: {team_name}")
            
            # Add KPI configs
            configured_kpis = list(iter_employee_kpi_configs(config)) if config else []
            if configured_kpis:
                for position_name, display_order, kpi in configured_kpis:
                    db.add(TeamKPIConfig(
                        team_id=team.id,
                        performance_level="Employee",
                        position_name=position_name,
                        kpi_key=kpi['key'],
                        kpi_label=kpi['label'],
                        weight=float(kpi['weight']),
                        direction=kpi['direction'],
                        unit=kpi['unit'],
                        color=kpi['color'],
                        actual_col=kpi['actual_col'],
                        target_col=kpi['target_col'],
                        achievement_col=kpi.get('achievement_col'),
                        volume_unit=kpi.get('volume_unit'),
                        perspective=kpi.get('perspective'),
                        display_order=display_order,
                    ))
            else:
                kpi_weights = request.kpi_weights or {'attendance': 0.3, 'productivity': 0.4, 'quality': 0.3}
                for kpi_key, weight in kpi_weights.items():
                    kpi_config = TeamKPIConfig(
                        team_id=team.id,
                        kpi_key=kpi_key,
                        kpi_label=kpi_key.title(),
                        weight=float(weight),
                        direction='higher_better',
                        unit='%',
                        color='#10B981',
                        actual_col=f'{kpi_key}_actual',
                        target_col=f'{kpi_key}_target',
                        display_order=0,
                    )
                    db.add(kpi_config)
            
            db.commit()

            return True, TeamService._build_team_payload(team, db), errors
        
        except Exception as e:
            errors.append(f"Failed to create team: {str(e)}")
            logger.error(f"Create team error: {e}")
            db.rollback()
            return False, {}, errors
        
        finally:
            db.close()

    @staticmethod
    def update_team(team_name: str, request: TeamUpdateRequest) -> Tuple[bool, Dict[str, Any], List[str]]:
        """
        Update team in database.
        
        Args:
            team_name: Team name
            request: Update request
            
        Returns:
            Tuple (success, updated_team_dict, errors)
        """
        errors = []
        
        db = SessionLocal()
        try:
            repo = TeamRepository(db, Team)
            team = repo.get_by_name(team_name)
            
            if not team:
                errors.append(f"Team '{team_name}' not found")
                return False, {}, errors
            
            # Update fields
            update_data = {}
            if request.region:
                update_data['region'] = request.region
            if request.is_active is not None:
                update_data['is_active'] = request.is_active
            
            if update_data:
                updated_team = repo.update(team.id, update_data)
            else:
                updated_team = team
            
            # Update KPI weights if provided
            if request.kpi_weights:
                # Delete old configs
                db.query(TeamKPIConfig).filter(TeamKPIConfig.team_id == team.id).delete()
                
                # Add new configs
                for kpi_key, weight in request.kpi_weights.items():
                    kpi_config = TeamKPIConfig(
                        team_id=team.id,
                        kpi_key=kpi_key,
                        kpi_label=kpi_key.title(),
                        weight=float(weight),
                        direction='higher_better',
                        unit='%',
                        color='#10B981',
                        actual_col=f'{kpi_key}_actual',
                        target_col=f'{kpi_key}_target',
                        display_order=0,
                    )
                    db.add(kpi_config)
                
                db.commit()
            
            logger.info(f"Updated team: {team_name}")
            
            # Return updated team
            kpi_configs = db.query(TeamKPIConfig).filter(TeamKPIConfig.team_id == team.id).all()
            
            return True, TeamService._build_team_payload(updated_team, db), errors
        
        except Exception as e:
            errors.append(f"Failed to update team: {str(e)}")
            logger.error(f"Update team error: {e}")
            db.rollback()
            return False, {}, errors
        
        finally:
            db.close()

    @staticmethod
    def delete_team(team_name: str) -> Tuple[bool, List[str]]:
        """
        Delete team (soft delete - mark as inactive).
        
        Args:
            team_name: Team name
            
        Returns:
            Tuple (success, errors)
        """
        errors = []
        
        db = SessionLocal()
        try:
            repo = TeamRepository(db, Team)
            team = repo.get_by_name(team_name)
            
            if not team:
                errors.append(f"Team '{team_name}' not found")
                return False, errors
            
            # Soft delete
            success = repo.soft_delete(team.id)
            
            if success:
                logger.info(f"Deleted team: {team_name}")
                return True, errors
            else:
                errors.append("Failed to delete team")
                return False, errors
        
        except Exception as e:
            errors.append(f"Failed to delete team: {str(e)}")
            logger.error(f"Delete team error: {e}")
            db.rollback()
            return False, errors
        
        finally:
            db.close()

    @staticmethod
    def validate_team(team_name: str) -> Tuple[bool, List[str], List[str]]:
        """
        Validate team configuration.
        
        Args:
            team_name: Team name
            
        Returns:
            Tuple (is_valid, errors, warnings)
        """
        errors = []
        warnings = []
        
        db = SessionLocal()
        try:
            repo = TeamRepository(db, Team)
            team = repo.get_by_name(team_name)
            
            if not team:
                errors.append(f"Team '{team_name}' not found")
                return False, errors, warnings
            
            # Validate KPI config
            kpi_configs = db.query(TeamKPIConfig).filter(TeamKPIConfig.team_id == team.id).all()
            
            if not kpi_configs:
                errors.append("No KPI configurations defined")
            else:
                totals = {}
                for kpi in kpi_configs:
                    totals[kpi.performance_level] = totals.get(kpi.performance_level, 0.0) + float(kpi.weight)
                for level, total_weight in totals.items():
                    if total_weight > 1.01:
                        errors.append(f"{level} KPI weights exceed 1.0 (got {total_weight})")
            
            try:
                config = TeamService._load_team_config(team.name, team.db_name)
                if not config:
                    warnings.append("No JSON team config found; new-team onboarding still needs a config file")
            except Exception as e:
                warnings.append(f"Could not load team config: {e}")
            
            # Warnings
            if not team.is_active:
                warnings.append("Team is marked as inactive")
            
            # Check if cleaner available
            try:
                available_cleaners = CleanerFactory.get_available_teams()
                if team_name not in available_cleaners:
                    warnings.append(f"No data cleaner available for {team_name}")
            except Exception:
                pass
            
            is_valid = len(errors) == 0
            return is_valid, errors, warnings
        
        except Exception as e:
            errors.append(f"Failed to validate team: {str(e)}")
            logger.error(f"Validate team error: {e}")
            return False, errors, warnings
        
        finally:
            db.close()

    @staticmethod
    def _is_valid_team_name(team_name: str) -> bool:
        """
        Validate team name format.
        
        Args:
            team_name: Team name to validate
            
        Returns:
            True if valid
        """
        if not team_name:
            return False
        
        allowed_chars = set('abcdefghijklmnopqrstuvwxyz0123456789_')
        return all(c in allowed_chars for c in team_name)

    @staticmethod
    def get_team_statistics() -> Dict[str, Any]:
        """
        Get statistics about teams from database.
        
        Returns:
            Dictionary with team statistics
        """
        db = SessionLocal()
        try:
            repo = TeamRepository(db, Team)
            all_teams = [team for team in repo.get_all() if team.team_level == "employee"]
            active_teams = repo.get_active_teams(team_level="employee")
            
            # Get all regions
            regions = set()
            for team in all_teams:
                regions.add(team.region)
            
            # Get all KPI keys
            employee_team_ids = [team.id for team in all_teams]
            kpi_configs = (
                db.query(TeamKPIConfig)
                .filter(TeamKPIConfig.team_id.in_(employee_team_ids))
                .all()
                if employee_team_ids
                else []
            )
            kpi_keys = set(kpi.kpi_key for kpi in kpi_configs)
            
            return {
                'total_teams': len(all_teams),
                'active_teams': len(active_teams),
                'inactive_teams': len(all_teams) - len(active_teams),
                'regions': list(regions),
                'total_kpi_keys': len(kpi_keys),
            }
        
        except Exception as e:
            logger.error(f"Failed to get team statistics: {e}")
            raise
        
        finally:
            db.close()
