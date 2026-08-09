"""
Team Data Models
Pydantic models for team configuration and management.
"""

from pydantic import BaseModel, Field, validator
from typing import Dict, List, Optional, Literal
from datetime import datetime


class TeamConfig(BaseModel):
    """Team configuration details."""
    
    name: str = Field(..., min_length=1, max_length=100, description="Team name")
    display_name: str = Field(..., min_length=1, description="Display name for UI")
    region: Literal['EGY', 'UAE', 'Other'] = Field(default='EGY', description="Team region")
    description: Optional[str] = Field(None, description="Team description")
    
    # KPI Configuration
    kpi_keys: List[str] = Field(default_factory=list, description="KPI metrics for team")
    kpi_weights: Dict[str, float] = Field(default_factory=dict, description="KPI weight configuration")
    
    # Data Configuration
    data_source: Literal['Excel', 'CSV', 'Database'] = Field(default='Excel')
    data_file_pattern: Optional[str] = Field(None, description="File naming pattern (e.g., 'Q4_2024_*.xlsx')")
    
    # Contact
    team_lead: Optional[str] = Field(None, description="Team lead name")
    team_lead_email: Optional[str] = Field(None, description="Team lead email")
    
    # Status
    is_active: bool = Field(default=True, description="Team is active")
    created_at: Optional[datetime] = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now)
    
    @validator('kpi_weights')
    def weights_sum_to_one(cls, v):
        """Validate that KPI weights sum to 1.0."""
        if v:
            total = sum(v.values())
            if total > 0 and abs(total - 1.0) > 0.01:
                raise ValueError(f"KPI weights must sum to 1.0, got {total}")
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "name": "inbound",
                "display_name": "Inbound Team",
                "region": "EGY",
                "description": "Inbound call center team",
                "kpi_keys": ["attendance", "productivity", "quality"],
                "kpi_weights": {"attendance": 0.3, "productivity": 0.4, "quality": 0.3},
                "data_source": "Excel",
                "team_lead": "Ahmed Hassan",
                "team_lead_email": "ahmed@company.com",
                "is_active": True,
            }
        }


class TeamCreateRequest(BaseModel):
    """Request to create a new team."""
    
    name: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(...)
    region: Literal['EGY', 'UAE', 'Other'] = Field(default='EGY')
    description: Optional[str] = None
    kpi_keys: Optional[List[str]] = Field(default_factory=list)
    kpi_weights: Optional[Dict[str, float]] = Field(default_factory=dict)
    team_lead: Optional[str] = None
    team_lead_email: Optional[str] = None
    
    @validator('name')
    def name_lowercase_no_spaces(cls, v):
        """Team name must be lowercase, no spaces."""
        v = v.lower().replace(' ', '_')
        return v


class TeamUpdateRequest(BaseModel):
    """Request to update a team."""
    
    display_name: Optional[str] = None
    description: Optional[str] = None
    region: Optional[Literal['EGY', 'UAE', 'Other']] = None
    kpi_keys: Optional[List[str]] = None
    kpi_weights: Optional[Dict[str, float]] = None
    team_lead: Optional[str] = None
    team_lead_email: Optional[str] = None
    is_active: Optional[bool] = None
    
    @validator('kpi_weights')
    def weights_sum_to_one(cls, v):
        """Validate that KPI weights sum to 1.0."""
        if v:
            total = sum(v.values())
            if total > 0 and abs(total - 1.0) > 0.01:
                raise ValueError(f"KPI weights must sum to 1.0, got {total}")
        return v


class TeamResponse(BaseModel):
    """Response containing team information."""
    
    id: str
    name: str
    display_name: str
    region: str
    team_level: Literal['employee', 'management']
    description: Optional[str]
    kpi_keys: List[str]
    kpi_weights: Dict[str, float]
    data_source: str
    team_lead: Optional[str]
    team_lead_email: Optional[str]
    is_active: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class TeamListResponse(BaseModel):
    """Response containing list of teams."""
    
    teams: List[TeamResponse]
    total: int
    active_count: int
    inactive_count: int


class TeamValidationResponse(BaseModel):
    """Response from team validation."""
    
    valid: bool
    team_name: str
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    message: str
    
    class Config:
        schema_extra = {
            "example": {
                "valid": True,
                "team_name": "inbound",
                "errors": [],
                "warnings": ["Team has no team lead assigned"],
                "message": "Team configuration is valid with warnings"
            }
        }


class TeamOnboardingStep(BaseModel):
    """Single step in team onboarding process."""
    
    step_number: int
    name: str
    description: str
    required: bool = True
    completed: bool = False
    error: Optional[str] = None


class TeamOnboardingRequest(BaseModel):
    """Request to start team onboarding."""
    
    team_name: str
    auto_proceed: bool = Field(default=False, description="Auto-proceed through all steps")
    send_notifications: bool = Field(default=True, description="Send socket notifications")


class TeamOnboardingResponse(BaseModel):
    """Response from team onboarding."""
    
    team_name: str
    status: Literal['pending', 'in_progress', 'completed', 'failed']
    current_step: int
    total_steps: int
    steps: List[TeamOnboardingStep]
    overall_message: str
    estimated_time_seconds: Optional[int]
