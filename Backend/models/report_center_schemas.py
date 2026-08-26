from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class ReportCenterFilters(BaseModel):
    """Normalized filters shared by the Reports Center summary and records APIs."""

    period: str | None = None
    comparison_period: str | None = None
    region: str | None = None
    team: str | None = None
    performance_level: str | None = None
    position: str | None = None
    employee_id: str | None = None
    grade: str | None = None
    status: str | None = None
    kpi: str | None = None
    cursor: str | None = Field(default=None, max_length=500)
    page_size: int = Field(default=50, ge=1, le=100)
    include_total: bool = False

    @field_validator("performance_level", mode="before")
    @classmethod
    def normalize_performance_level(cls, value: Any) -> str | None:
        """Keep the Reports UI's All levels value aggregate-friendly."""
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized or normalized.casefold() == "all":
            return None
        return normalized

    @field_validator(
        "period",
        "comparison_period",
        "region",
        "team",
        "performance_level",
        "position",
        "employee_id",
        "grade",
        "status",
        "kpi",
        "cursor",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    def as_query(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class ReportCenterCapabilities(BaseModel):
    role: str
    can_export: bool = False
    can_view_people: bool = False
    can_view_actions: bool = False
    allowed_formats: list[str] = Field(default_factory=list)


class ReportCenterResponse(BaseModel):
    role: str
    filters: dict[str, Any] = Field(default_factory=dict)
    period: dict[str, Any] | None = None
    comparison_period: dict[str, Any] | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    trend: list[dict[str, Any]] = Field(default_factory=list)
    team_comparison: list[dict[str, Any]] = Field(default_factory=list)
    kpi_health: list[dict[str, Any]] = Field(default_factory=list)
    insights: dict[str, Any] = Field(default_factory=dict)
    corrective_actions: dict[str, Any] | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    capabilities: ReportCenterCapabilities
    as_of: str
    data_version: int


class ReportCenterRecordsResponse(BaseModel):
    role: str
    period: dict[str, Any] | None = None
    comparison_period: dict[str, Any] | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    items: list[dict[str, Any]] = Field(default_factory=list)
    page_size: int
    next_cursor: str | None = None
    has_more: bool = False
    total: int | None = None
    capabilities: ReportCenterCapabilities
    as_of: str
    data_version: int
