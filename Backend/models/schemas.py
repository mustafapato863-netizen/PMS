from pydantic import BaseModel, Field, field_validator
from typing import Any, Optional, Dict, List

class StandardResponse(BaseModel):
    success: bool
    message: str
    data: Any = None

class Employee(BaseModel):
    id: str
    name: str
    team: str
    status: str = "Active"
    hiring_date: Optional[str] = None
    region: Optional[str] = "EGY"
    performance_level: str = "Employee"
    position: Optional[str] = None

class GeoBreakdown(BaseModel):
    dubai: int = 0
    sharjah: int = 0
    ajman: int = 0
    clinics: int = 0

class GeoData(BaseModel):
    bookings: GeoBreakdown = Field(default_factory=GeoBreakdown)
    attended: GeoBreakdown = Field(default_factory=GeoBreakdown)

class CallsData(BaseModel):
    inbound: int = 0
    outbound: int = 0
    total_handled: int = 0
    abandoned: int = 0
    aht_raw: str = "00:00:00"

class ActualMetrics(BaseModel):
    booking_rate: float = 0.0
    attend_rate: float = 0.0
    abandon_rate: float = 0.0
    reachability_rate: float = 0.0
    rejection_rate: float = 0.0
    initial_error_rate: float = 0.0
    submission_rate: float = 0.0
    quality_rate: float = 0.0
    utz_rate: float = 0.0

class AchievementMetrics(BaseModel):
    booking_ach: float = 0.0
    attend_ach: float = 0.0
    quality_ach: float = 0.0
    aht_ach: float = 0.0
    reachability_ach: float = 0.0
    abandon_ach: float = 0.0
    rejection_ach: float = 0.0
    initial_error_ach: float = 0.0
    submission_ach: float = 0.0
    op_census_ach: float = 0.0
    op_revenue_ach: float = 0.0
    ip_census_ach: float = 0.0
    ip_revenue_ach: float = 0.0
    activity_ach: float = 0.0

class RootCauseInfo(BaseModel):
    kpi: str
    impact_pct: float
    actual: float
    target: float

class EvaluationData(BaseModel):
    score: float  # Normalized 0-100
    grade: str
    root_cause: Optional[RootCauseInfo] = None
    suggested_action: Optional[str] = None
    corrective_action: Optional[str] = None
    manager_notes: Optional[str] = None
    planning_category: Optional[List[str]] = Field(default_factory=list)
    trend_status: Optional[Dict[str, Any]] = Field(default_factory=dict)

class PerformanceRecord(BaseModel):
    id: str  # Canonical key: employee_id + "_" + year + "_" + month
    employee_id: str
    employee_name: str
    team: str
    month: str
    year: Optional[int] = None
    region: Optional[str] = "EGY"
    performance_level: str = "Employee"
    position: Optional[str] = None
    status: Optional[str] = None
    calls: CallsData = Field(default_factory=CallsData)
    geo: GeoData = Field(default_factory=GeoData)
    actual: ActualMetrics = Field(default_factory=ActualMetrics)
    achievement: AchievementMetrics = Field(default_factory=AchievementMetrics)
    evaluation: EvaluationData
    upload_id: Optional[str] = None
    raw_data: Dict[str, Any] = Field(default_factory=dict)
    kpi_values: List[Dict[str, Any]] = Field(default_factory=list)

class KPIWeight(BaseModel):
    team: str
    weights: Dict[str, float]

class Target(BaseModel):
    team: str
    targets: Dict[str, float]

class UploadRecord(BaseModel):
    id: str
    filename: str
    uploaded_at: str
    uploaded_by: str

class ManagerNote(BaseModel):
    employee_id: str
    month: str
    notes: str
    updated_at: str

class CorrectiveAction(BaseModel):
    id: Optional[str] = None
    employee_id: str
    employee_name: str
    team: str
    month: str
    score: float
    grade: str
    root_cause: str
    suggested_action: str
    manager_action: str
    manager_notes: str
    timestamp: str
    created_by_name: Optional[str] = None
    created_by_role: Optional[str] = None

class PlanningCategoryRecord(BaseModel):
    employee_id: str
    month: str
    category: str

class TeamAction(BaseModel):
    id: Optional[str] = None  # composite key: team_id + "_" + year + "_" + month
    team_id: str
    month: str
    year: Optional[int] = None
    overall_action: str
    updated_at: str
    updated_by: str = "Admin"

class UserRecord(BaseModel):
    id: str
    name: str = Field(..., min_length=1, max_length=255)
    username: str
    password: str
    role: str
    is_active: bool = True
    accessible_teams: Optional[List[str]] = None
    accessible_team_levels: Optional[List[tuple[str, str]]] = None
    is_general_manager: bool = False

class UserUpdateRecord(BaseModel):
    id: str
    name: str = Field(..., min_length=1, max_length=255)
    username: str
    role: str
    is_active: bool = True
    password: Optional[str] = None
    accessible_teams: Optional[List[str]] = None
    accessible_team_levels: Optional[List[tuple[str, str]]] = None
    is_general_manager: bool = False

class LoginPayload(BaseModel):
    username: str
    password: str
    remember_me: bool = False


class ProfileUpdatePayload(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)

    @field_validator("full_name")
    @classmethod
    def full_name_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Full name cannot be blank.")
        return normalized


class PasswordChangePayload(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=12, max_length=72)

    @field_validator("new_password")
    @classmethod
    def new_password_must_fit_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must not exceed 72 bytes.")
        return value

class JWTToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str
    expires_in: int
    csrf_token: str

