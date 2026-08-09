from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


PlanStatus = Literal["Draft", "In Progress", "At Risk", "Completed", "Archived"]
MilestoneStatus = Literal["Pending", "In Progress", "Completed"]


class PlanObjectiveInput(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    measurement_type: str = Field(min_length=2, max_length=30)
    baseline_value: float
    target_value: float
    current_value: float | None = None
    unit: str = Field(min_length=1, max_length=30)
    direction: Literal["higher_better", "lower_better"]
    due_date: date
    owner_user_id: UUID
    linked_kpi_keys: list[str] = Field(default_factory=list)
    is_required: bool = True

    @model_validator(mode="after")
    def measurable(self):
        if self.baseline_value == self.target_value:
            raise ValueError("Objective target must differ from its baseline")
        return self


class PlanKPIInput(BaseModel):
    kpi_key: str = Field(min_length=1, max_length=100)
    kpi_label: str = Field(min_length=1, max_length=255)
    unit: str = Field(min_length=1, max_length=30)
    direction: Literal["higher_better", "lower_better"]
    baseline_value: float
    target_value: float
    current_value: float | None = None
    contribution: float | None = None
    data_month: str | None = None
    data_year: int | None = Field(default=None, ge=2000, le=2100)


class PlanActionInput(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=3)
    action_type: Literal["Training", "Reward", "PIP", "Monitor", "Coaching", "Warning", "Promotion"] = "Monitor"
    owner_user_id: UUID
    due_date: date
    priority: Literal["Low", "Medium", "High", "Critical"] = "Medium"
    objective_index: int | None = Field(default=None, ge=0)
    linked_kpi_key: str | None = None
    employee_identifier: str | None = None


class PlanMilestoneInput(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    due_date: date
    owner_user_id: UUID
    note: str | None = None


class PlanMilestoneCreate(PlanMilestoneInput):
    status: MilestoneStatus = "Pending"


class PlanMilestoneUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=255)
    due_date: date | None = None
    owner_user_id: UUID | None = None
    status: MilestoneStatus | None = None
    note: str | None = None


class PlanCreate(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    scope_type: Literal["Team", "Position", "Employee", "Management"]
    team: str
    performance_level: Literal["Employee", "Managerial", "Corporate"]
    region: str | None = None
    position_name: str | None = None
    employee_identifier: str | None = None
    period_start: date
    period_end: date
    due_date: date
    owner_user_id: UUID
    baseline_value: float
    target_value: float
    current_value: float | None = None
    outcome_unit: str = "%"
    outcome_direction: Literal["higher_better", "lower_better"] = "higher_better"
    expected_impact: float | None = None
    insight_ids: list[str] = Field(default_factory=list)
    evidence_month: str | None = None
    evidence_year: int | None = Field(default=None, ge=2000, le=2100)
    no_insight_reason: str | None = None
    objectives: list[PlanObjectiveInput] = Field(min_length=1)
    kpis: list[PlanKPIInput] = Field(default_factory=list)
    actions: list[PlanActionInput] = Field(default_factory=list)
    milestones: list[PlanMilestoneInput] = Field(default_factory=list)
    activate: bool = False

    @model_validator(mode="after")
    def valid_context(self):
        if self.period_end < self.period_start or self.due_date < self.period_start:
            raise ValueError("Plan period and due date are invalid")
        if self.scope_type == "Position" and not self.position_name:
            raise ValueError("Position scope requires a position")
        if self.scope_type == "Employee" and not self.employee_identifier:
            raise ValueError("Employee scope requires an employee")
        if self.insight_ids and (not self.evidence_month or not self.evidence_year):
            raise ValueError("Linked insights require an evidence period")
        if not self.insight_ids and not (self.no_insight_reason or "").strip():
            raise ValueError("A plan without linked insights requires a reason")
        return self


class PlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=180)
    owner_user_id: UUID | None = None
    due_date: date | None = None
    target_value: float | None = None
    current_value: float | None = None
    expected_impact: float | None = None
    status: PlanStatus | None = None
    status_reason: str | None = None
    completion_note: str | None = None


class PlanItemUpdate(BaseModel):
    status: str | None = None
    current_value: float | None = None
    completion_note: str | None = None
    note: str | None = None


class PlanNoteCreate(BaseModel):
    text: str = Field(min_length=2, max_length=5000)
    review_month: str | None = None
    review_year: int | None = Field(default=None, ge=2000, le=2100)
