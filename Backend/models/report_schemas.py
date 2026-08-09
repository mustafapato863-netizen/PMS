from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


REPORT_TYPES = Literal[
    "executive",
    "team",
    "position",
    "employee",
    "grade_distribution",
    "corrective_actions",
    "kpi",
    "data_quality",
    "monthly_uae",
    "monthly_egypt",
    "team_marketing",
]

MONTHS = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}


class BlockConfigSchema(BaseModel):
    # Flexible container for any block settings
    settings: dict[str, Any] = Field(default_factory=dict)


class ReportBlockSchema(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=100)
    config: BlockConfigSchema = Field(default_factory=BlockConfigSchema)


class ReportSlideSchema(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=180)
    layout: str = Field(min_length=1, max_length=100)
    blocks: list[ReportBlockSchema] = Field(default_factory=list)


class ReportConfiguration(BaseModel):
    report_type: REPORT_TYPES
    report_name: str = Field(min_length=1, max_length=180)
    start_month: str
    start_year: int = Field(ge=2000, le=2100)
    end_month: str | None = None
    end_year: int | None = Field(default=None, ge=2000, le=2100)
    region: str | None = None
    team: str | None = None
    position: str | None = None
    performance_level: str | None = None
    employee_id: str | None = None
    grade: str | None = None
    status: str | None = None
    included_sections: list[str] = Field(default_factory=lambda: ["summary", "details"])
    output_format: str = "pptx"
    slides: list[ReportSlideSchema] = Field(default_factory=list)

    @field_validator("report_name")
    @classmethod
    def validate_report_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Report name cannot be empty")
        return value

    @field_validator("output_format", mode="before")
    @classmethod
    def validate_output_format(cls, value: str | None) -> str:
        normalized = str(value or "pptx").strip().lower()
        if normalized == "excel":
            return "pptx"
        if normalized not in {"pdf", "pptx"}:
            raise ValueError("Output format must be either pdf or pptx")
        return normalized

    @model_validator(mode="after")
    def validate_period(self):
        if self.start_month not in MONTHS:
            raise ValueError("Invalid start month")
        if (self.end_month is None) != (self.end_year is None):
            raise ValueError("End month and end year must be provided together")
        if self.end_month is not None:
            if self.end_month not in MONTHS:
                raise ValueError("Invalid end month")
            start = (self.start_year, MONTHS[self.start_month])
            end = (self.end_year or self.start_year, MONTHS[self.end_month])
            if end < start:
                raise ValueError("End period cannot be before start period")
        return self


class SaveReportTemplateRequest(BaseModel):
    template_name: str = Field(min_length=1, max_length=180)
    configuration: ReportConfiguration

    @field_validator("template_name")
    @classmethod
    def validate_template_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Template name cannot be empty")
        return value
