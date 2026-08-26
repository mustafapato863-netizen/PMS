from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


InsightSeverity = Literal["critical", "risk", "opportunity", "information"]
InsightType = Literal["performance", "kpi_driver", "employee_risk", "opportunity", "data_quality"]


class InsightPeriod(BaseModel):
    year: int
    month: str
    key: str


class InsightEvidence(BaseModel):
    label: str
    value: str


class InsightDetail(BaseModel):
    current_value: float | None = None
    previous_value: float | None = None
    target_value: float | None = None
    unit: str | None = None
    direction: str | None = None
    impact_points: float | None = None
    affected_teams: list[str] = Field(default_factory=list)
    affected_positions: list[str] = Field(default_factory=list)
    affected_employees: list[str] = Field(default_factory=list)
    evidence: list[InsightEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommended_focus: str


class InsightItem(BaseModel):
    id: str
    severity: InsightSeverity
    insight_type: InsightType
    title: str
    explanation: str
    scope: str
    impact_points: float | None = None
    trend_label: str
    priority_reason: str
    status: str = "open"
    team: str | None = None
    performance_level: str | None = None
    position: str | None = None
    employee_id: str | None = None
    kpi_key: str | None = None
    included_in_score: bool = True
    weight: float | None = None
    evidence_classification: str | None = None
    detail: InsightDetail
    planning_context: dict[str, str | float | None] = Field(default_factory=dict)


class InsightDriver(BaseModel):
    id: str
    driver: str
    scope: str
    impact_points: float
    direction: Literal["positive", "negative"]
    insight_id: str
    trend: list["InsightDriverTrendPoint"] = Field(default_factory=list)


class InsightDriverTrendPoint(BaseModel):
    period: InsightPeriod
    impact_points: float | None = None


class InsightRisk(BaseModel):
    key: str
    label: str
    count: int
    explanation: str
    filter_type: str


class InsightSummary(BaseModel):
    critical: int = 0
    at_risk: int = 0
    opportunities: int = 0
    data_issues: int = 0
    critical_issues: int = 0
    negative_weighted_drivers: int = 0
    positive_weighted_drivers: int = 0
    weighted_negative_impact: float = 0
    weighted_positive_impact: float = 0
    weighted_net_impact: float = 0
    analyzed_kpis: int = 0
    expected_kpis: int = 0
    coverage_percent: float | None = None


class InsightTeamSummary(BaseModel):
    team: str
    current_score: float | None = None
    previous_score: float | None = None
    score_change: float | None = None
    gap_points: float | None = None
    gap_contribution_percent: float | None = None
    impacted_employees: int = 0
    total_employees: int = 0
    affected_percentage: float | None = None
    critical: int = 0
    at_risk: int = 0
    opportunities: int = 0
    main_insight_id: str | None = None
    main_cause: str | None = None


class InsightScopeSummary(BaseModel):
    scope: str
    current_score: float | None = None
    previous_score: float | None = None
    score_change: float | None = None
    gap_points: float | None = None
    gap_contribution_percent: float | None = None
    impacted_employees: int = 0
    total_employees: int = 0
    affected_percentage: float | None = None


class InsightExecutiveStory(BaseModel):
    headline: str
    scope_label: str
    current_score: float | None = None
    target_score: float = 100.0
    gap_points: float | None = None
    score_change: float | None = None
    primary_scope: str | None = None
    primary_scope_contribution_percent: float | None = None
    primary_driver: str | None = None
    primary_driver_impact: float | None = None
    recommended_focus: str
    confidence: Literal["high", "partial", "low"] = "high"
    evidence: list[InsightEvidence] = Field(default_factory=list)


class InsightPersonContribution(BaseModel):
    employee_id: str
    employee_name: str
    team: str
    performance_level: str
    position: str
    kpi_key: str
    kpi_label: str
    unit: str | None = None
    direction: str | None = None
    current_value: float | None = None
    target_value: float | None = None
    gap: float | None = None
    weighted_impact: float | None = None
    trend: float | None = None
    severity: str
    classification: Literal["negative", "positive", "affected", "data_issue"]


class InsightPeopleContributionAnalysis(BaseModel):
    kpi_key: str
    kpi_label: str
    unit: str | None = None
    direction: str | None = None
    total_employees: int = 0
    negative_contributors: int = 0
    positive_contributors: int = 0
    data_issues: int = 0
    rows: list[InsightPersonContribution] = Field(default_factory=list)


class InsightKpiTrendPoint(BaseModel):
    period: InsightPeriod
    actual_value: float | None = None
    target_value: float | None = None
    measured_records: int = 0


class InsightKpiTrend(BaseModel):
    kpi_key: str
    kpi_label: str
    unit: str | None = None
    direction: str | None = None
    points: list[InsightKpiTrendPoint] = Field(default_factory=list)


class InsightRoleSummary(BaseModel):
    role: str
    team: str
    current_score: float | None = None
    previous_score: float | None = None
    movement: float | None = None
    net_impact: float | None = None
    affected_employees: int = 0
    total_employees: int = 0
    primary_insight_id: str | None = None


class InsightKpiOverviewPoint(BaseModel):
    period: InsightPeriod
    total_kpis: int = 0
    on_track: int = 0
    at_risk: int = 0
    critical: int = 0


class InsightKpiOverview(BaseModel):
    total_kpis: int = 0
    on_track: int = 0
    at_risk: int = 0
    critical: int = 0
    points: list[InsightKpiOverviewPoint] = Field(default_factory=list)


class InsightFilterOptions(BaseModel):
    periods: list[InsightPeriod] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    teams: list[str] = Field(default_factory=list)
    performance_levels: list[str] = Field(default_factory=list)
    positions: list[str] = Field(default_factory=list)
    employees: list[dict[str, str]] = Field(default_factory=list)
    kpis: list[dict[str, str]] = Field(default_factory=list)
    severities: list[str] = Field(default_factory=lambda: ["critical", "risk", "opportunity", "information"])
    insight_types: list[str] = Field(default_factory=lambda: ["performance", "kpi_driver", "employee_risk", "opportunity", "data_quality"])
    statuses: list[str] = Field(default_factory=lambda: ["open"])


class InsightComparison(BaseModel):
    current: InsightPeriod | None = None
    previous: InsightPeriod | None = None
    is_adjacent: bool = False
    note: str | None = None


class InsightsWorkspace(BaseModel):
    summary: InsightSummary
    priority_insights: list[InsightItem]
    team_analyses: list[InsightItem] = Field(default_factory=list)
    performance_drivers: list[InsightDriver]
    risks: list[InsightRisk]
    opportunities: list[InsightItem]
    data_issues: list[InsightItem]
    team_summaries: list[InsightTeamSummary] = Field(default_factory=list)
    geography_summaries: list[InsightScopeSummary] = Field(default_factory=list)
    executive_story: InsightExecutiveStory | None = None
    people_contribution_analysis: InsightPeopleContributionAnalysis | None = None
    kpi_trend: InsightKpiTrend | None = None
    role_summaries: list[InsightRoleSummary] = Field(default_factory=list)
    kpi_overview: InsightKpiOverview = Field(default_factory=InsightKpiOverview)
    options: InsightFilterOptions
    comparison: InsightComparison
    deferred_capabilities: list[str] = Field(default_factory=list)


class InsightsWorkspaceResponse(BaseModel):
    success: bool
    message: str
    data: InsightsWorkspace
