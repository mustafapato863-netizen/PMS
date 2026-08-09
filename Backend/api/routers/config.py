"""
Configuration API endpoints.
Provides read-only access to team configurations from the backend.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List

# Import config loader
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.loader import (
    ConfigurationError,
    load_team_config,
    load_all_team_configs,
    get_team_names,
    resolve_team_config,
)

router = APIRouter()


@router.get("/config/teams")
async def get_all_team_configs() -> Dict[str, Any]:
    """
    Get all team configurations.
    
    Returns:
        {
          "success": true,
          "data": [
            {
              "team": "Inbound",
              "db_name": "Inbound",
              "region": "EGY",
              "grade_thresholds": {...},
              "kpis": [...]
            },
            ...
          ]
        }
    """
    try:
        configs = load_all_team_configs()
        return {
            "success": True,
            "data": configs
        }
    except ValueError as e:
        raise HTTPException(status_code=500, detail="Failed to load team configurations.") from e


@router.get("/config/teams/{team_name}")
async def get_team_config(
    team_name: str,
    performance_level: str | None = Query(None),
    position: str | None = Query(None),
) -> Dict[str, Any]:
    """
    Get configuration for a specific team.
    
    Args:
        team_name: Name of the team (e.g., "Inbound", "Sales")
        
    Returns:
        {
          "success": true,
          "data": {
            "team": "Inbound",
            "db_name": "Inbound",
            "region": "EGY",
            "grade_thresholds": {...},
            "kpis": [...]
          }
        }
    """
    try:
        config = load_team_config(team_name)
        if not config:
            raise HTTPException(
                status_code=404,
                detail=f"Team configuration not found: {team_name}"
            )
        if performance_level or position:
            config = resolve_team_config(
                config,
                performance_level or "Employee",
                position,
            )
        return {
            "success": True,
            "data": config
        }
    except ConfigurationError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/config/teams/names/list")
async def get_team_names_list() -> Dict[str, Any]:
    """
    Get list of all available team names.
    Useful for dropdowns and team selectors in UI.
    
    Returns:
        {
          "success": true,
          "data": ["Inbound", "Outbound", "Sales", ...]
        }
    """
    try:
        names = get_team_names()
        return {
            "success": True,
            "data": names
        }
    except ValueError as e:
        raise HTTPException(status_code=500, detail="Failed to load team configuration.") from e
