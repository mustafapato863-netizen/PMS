from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


BlockType = Literal[
    "cover_title", "agenda", "executive_kpi_summary", "offshore_summary", "department_summary", "team_summary", "position_summary", "employee_summary",
    "team_performance_overview", "team_performance_analysis", "actions_summary", "insights_summary", "team_risk_matrix",
    "performance_status", "score_trend", "grade_distribution", "team_ranking", "position_ranking",
    "overall_score_comparison", "actual_vs_target", "department_ranking", "kpi_performance", "performance_gap_drivers", "weighted_performance_gap", "lost_points_analysis", "contribution_waterfall", "top_performers",
    "bottom_performers", "employees_below_target", "employee_performance", "corrective_actions",
    "lowest_employees", "consecutive_low_performers", "overall_score_movement", "lowest_indicators", "root_cause_analysis", "process_issues", "staff_issues", "opportunities",
    "process_action_plan", "staff_action_plan", "feedback_sessions_status", "planning_progress", "milestone_overview", "at_risk_plans", "actions_by_owner", "critical_insights",
    "recommendations", "decisions_required", "system_analysis", "management_commentary", "executive_summary", "final_conclusion", "next_steps",
    "data_quality_summary", "missing_period_data", "invalid_targets", "missing_configuration", "upload_error_table",
    "overall_score_movement_bridge", "lowest_kpis_weighted_impact", "lowest_employees_current_period",
    "three_month_consecutive_low_performers", "applied_configuration_audit", "root_cause_evidence_matrix",
]

SlideLayout = Literal[
    "cover", "full_width", "two_blocks", "four_kpis", "kpi_chart", "kpi_chart_narrative", "two_charts",
    "chart_table", "chart_narrative", "table_narrative", "two_tables", "comparison", "risk_actions",
    "insights_decisions", "actions_planning", "closing_decisions", "department_divider", "root_cause_actions",
    "process_staff_actions", "feedback_status", "decisions_next_steps", "closing_page", "team_review",
]


class ReportPeriod(BaseModel):
    month: Literal["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    year: int = Field(ge=2000, le=2100)


class ReportScope(BaseModel):
    region: str | None = None
    team: str | None = None
    position: str | None = None
    performance_level: str | None = None
    employee_id: str | None = None
    grade: str | None = None
    status: str | None = None


class BlockConfig(BaseModel):
    title: str | None = Field(default=None, max_length=180)
    metrics: list[str] = Field(default_factory=list)
    comparison: bool = True
    number_format: Literal["standard", "compact", "percent", "currency"] = "standard"
    row_limit: int = Field(default=10, ge=1, le=50)
    sort_by: str | None = None
    sort_direction: Literal["asc", "desc"] = "desc"
    show_icons: bool = True
    show_subtitle: bool = True
    show_data_labels: bool = True
    show_target: bool = True
    narrative_mode: Literal["auto", "manual", "auto_commentary"] = "auto"
    include_evidence: bool = True
    include_recommendations: bool = True
    max_length: int = Field(default=700, ge=100, le=2000)
    scope_override: dict[str, str] = Field(default_factory=dict)


class ReportBlock(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    type: BlockType
    slot: str = Field(min_length=1, max_length=50)
    config: BlockConfig = Field(default_factory=BlockConfig)


class ReportSlide(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=180)
    layout: SlideLayout
    order: int = Field(ge=0)
    blocks: list[ReportBlock] = Field(default_factory=list)


class ReportStoryMetadata(BaseModel):
    mode: Literal["standard", "full", "compact"] = "standard"
    fixed_page_count: int = Field(default=0, ge=0)
    pages_per_team: int = Field(default=0, ge=0, le=10)
    outline: list[str] = Field(default_factory=list)
    recommended: bool = False


class ReportTemplateDefinition(BaseModel):
    slides: list[ReportSlide]
    theme_key: str = "sgh_default"
    language: Literal["en", "ar"] = "en"
    preferred_format: Literal["pptx", "pdf"] = "pdf"
    story_metadata: ReportStoryMetadata = Field(default_factory=ReportStoryMetadata)


class GeneratedNarrative(BaseModel):
    block_id: str
    text: str
    generated_at: str
    evidence: list[str] = Field(default_factory=list)


class ManagementCommentary(BaseModel):
    entries: dict[str, str] = Field(default_factory=dict)


class ReportDraftDefinition(ReportTemplateDefinition):
    narratives: dict[str, GeneratedNarrative] = Field(default_factory=dict)


class ReportValidationIssue(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    slide_id: str | None = None
    block_id: str | None = None


class ReportValidationResult(BaseModel):
    valid: bool
    issues: list[ReportValidationIssue] = Field(default_factory=list)
    validated_at: str


class ReportTemplateCreate(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    template_key: str = Field(pattern=r"^[a-z0-9_\-]+$", max_length=100)
    report_type: str = Field(min_length=2, max_length=50)
    description: str = Field(default="", max_length=1000)
    visibility: Literal["private", "organization"] = "private"
    definition: ReportTemplateDefinition


class ReportDraftCreate(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    report_type: str = Field(min_length=2, max_length=50)
    template_id: str | None = None
    scope: ReportScope
    primary_period: ReportPeriod
    comparison_period: ReportPeriod | None = None

    @model_validator(mode="after")
    def comparison_precedes_primary(self):
        if self.comparison_period:
            months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
            primary = self.primary_period.year * 12 + months.index(self.primary_period.month)
            comparison = self.comparison_period.year * 12 + months.index(self.comparison_period.month)
            if comparison >= primary:
                raise ValueError("Comparison period must be earlier than the primary period")
        return self


class ReportDraftUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=3, max_length=180)
    definition: ReportDraftDefinition | None = None
    management_commentary: ManagementCommentary | None = None


class ReportGenerateRequest(BaseModel):
    expected_version: int = Field(ge=1)
    output_format: Literal["pdf"] = "pdf"


class BlockDataResult(BaseModel):
    block_id: str
    block_type: str
    state: Literal["ready", "no_data", "incomplete_configuration", "permission_denied", "source_unavailable"]
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    source_periods: list[str] = Field(default_factory=list)


class ManagementContract(BaseModel):
    model_config = ConfigDict(extra="allow")


class ScoreMovementBridgeContract(ManagementContract):
    previous_overall_score: float | None
    current_overall_score: float | None
    total_score_point_change: float | None
    comparison_period: str | None
    current_period: str | None
    matched_employee_count: int
    joiner_count: int
    leaver_count: int
    kpi_contribution_movements: list[dict[str, Any]]
    team_contribution_movements: list[dict[str, Any]]
    residual: float | None
    reconciliation_state: Literal["reconciled", "partial", "unavailable"]
    narrative: str
    warnings: list[str]


class WeightedKpiImpactContract(ManagementContract):
    rows: list[dict[str, Any]]
    configuration_issues_excluded: list[dict[str, Any]]
    ranking_method: str


class LowestEmployeesContract(ManagementContract):
    rows: list[dict[str, Any]]


class ConsecutiveLowPerformersContract(ManagementContract):
    rows: list[dict[str, Any]]
    insufficient_history: list[dict[str, Any]]
    required_periods: list[str]


class AppliedConfigurationAuditContract(ManagementContract):
    rows: list[dict[str, Any]]
    summary: dict[str, int]
    diagnostic_only: bool = True


class RootCauseEvidenceMatrixContract(ManagementContract):
    rows: list[dict[str, Any]]
    groups: dict[str, list[dict[str, Any]]]
    impact_label: str


MANAGEMENT_BLOCK_CONTRACTS = {
    "overall_score_movement_bridge": ScoreMovementBridgeContract,
    "lowest_kpis_weighted_impact": WeightedKpiImpactContract,
    "lowest_employees_current_period": LowestEmployeesContract,
    "three_month_consecutive_low_performers": ConsecutiveLowPerformersContract,
    "applied_configuration_audit": AppliedConfigurationAuditContract,
    "root_cause_evidence_matrix": RootCauseEvidenceMatrixContract,
}


class SlideDataResult(BaseModel):
    slide_id: str
    blocks: dict[str, BlockDataResult]
    resolved_at: str


class LegacyReportBlockSchema(BaseModel):
    id: str
    type: str
    config: dict[str, Any] = Field(default_factory=dict)


class LegacyReportSlideSchema(BaseModel):
    id: str
    title: str
    layout: str
    blocks: list[LegacyReportBlockSchema] = Field(default_factory=list)


class DraftPeriodChange(BaseModel):
    primary_period: ReportPeriod
    comparison_period: ReportPeriod | None = None

    @model_validator(mode="after")
    def comparison_precedes_primary(self):
        ReportDraftCreate(
            name="Period validation",
            report_type="validation",
            scope=ReportScope(),
            primary_period=self.primary_period,
            comparison_period=self.comparison_period,
        )
        return self


class ReportTemplateUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=3, max_length=180)
    description: str | None = Field(default=None, max_length=1000)
    visibility: Literal["private", "organization"] | None = None
    definition: ReportTemplateDefinition | None = None


class NarrativeRegenerateRequest(BaseModel):
    expected_version: int = Field(ge=1)
    slide_id: str | None = None


class ReportDefinitionEnvelope(BaseModel):
    definition: ReportDraftDefinition
    commentary: ManagementCommentary

    @model_validator(mode="after")
    def commentary_targets_known_blocks(self):
        block_ids = {block.id for slide in self.definition.slides for block in slide.blocks}
        unknown = set(self.commentary.entries) - block_ids
        if unknown:
            raise ValueError("Management commentary references an unknown report block")
        return self
