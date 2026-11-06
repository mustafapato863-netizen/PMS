from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


RouterIntentType = Literal[
    "current_value",
    "actual_vs_target",
    "compare_periods",
    "compare_branches",
    "compare_teams",
    "trend",
    "ranking",
    "score_drivers",
    "scorecard_structure",
    "corrective_actions",
    "clarify",
    "unsupported",
]

ClarificationCodeType = Literal[
    "NONE",
    "AMBIGUOUS_ABANDON_METRIC",
    "AMBIGUOUS_ATTENDANCE_DEFINITION",
    "AMBIGUOUS_TEAM_SCOPE",
    "AMBIGUOUS_KPI_SCOPE",
    "AMBIGUOUS_PERSON",
    "AMBIGUOUS_RANKING_METRIC",
    "AMBIGUOUS_COUNT_VS_RATE",
    "MISSING_COMPARISON_PERIOD",
    "MISSING_HR_JOIN_DATE",
    "RESTRICTED_SCOPE_SUGGESTION",
    "UNAVAILABLE_PERIOD_SUGGESTION",
]

TurnOutcomeType = Literal[
    "answer",
    "clarification",
    "restricted_access",
    "unavailable_data",
    "unsupported_request",
]

TurnKindV2 = Literal[
    "social",
    "analytical",
    "clarification",
    "correction",
    "unsupported",
]

OperationKindV2 = Literal[
    "greeting",
    "thanks",
    "current_value",
    "actual_vs_target",
    "compare_periods",
    "compare_branches",
    "compare_teams",
    "trend",
    "ranking",
    "person_summary",
    "person_best_period",
    "person_tenure_check",
    "score_drivers",
    "scorecard_structure",
    "corrective_actions",
]

MetricValueKindType = Literal[
    "count",
    "rate",
    "duration",
    "currency",
    "score",
    "diagnostic_indicator",
]


class QueryScopeV2(BaseModel):
    function: str | None = "Call Center"
    team: str | None = None
    position_group: str | None = None
    position: str | None = None
    performance_level: Literal["Employee", "Managerial", "Corporate"] = "Employee"
    branches: list[str] = Field(default_factory=list)
    periods: list[str] = Field(default_factory=list)
    period_window: Literal["explicit", "latest_published", "all_published", "trailing_6_months"] = "latest_published"
    employee_id: str | None = None
    employee_placeholder: str | None = None


class QueryOperationV2(BaseModel):
    operation_id: str
    kind: OperationKindV2
    metric_id: str | None = None
    value_kind: MetricValueKindType | None = None
    dimension: Literal["employee", "position", "team", "branch", "period", "kpi"] | None = None
    direction: Literal["best", "worst", "higher", "lower"] | None = None
    limit: int = Field(default=1, ge=1, le=10)
    include_ties: bool = True


class ValidatedQueryPlanV2(BaseModel):
    schema_version: Literal["pms-ai-query-v2"] = "pms-ai-query-v2"
    turn_kind: TurnKindV2 = "analytical"
    scope: QueryScopeV2 = Field(default_factory=QueryScopeV2)
    operations: list[QueryOperationV2] = Field(default_factory=list, max_length=2)
    clarification_code: ClarificationCodeType = "NONE"
    resolution_source: Literal["local_rules", "local_classifier", "gemini_router", "clarification_choice"] = "local_rules"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ClarificationChoice(BaseModel):
    id: str
    label: str
    description: str | None = None
    prompt_to_send: str
    team: str | None = None
    position: str | None = None
    metric_id: str | None = None
    performance_level: str | None = None
    period: str | None = None
    branch: str | None = None
    employee_id: str | None = None
    employee_name: str | None = None


class AiClarificationPrompt(BaseModel):
    code: ClarificationCodeType
    question: str
    choices: list[ClarificationChoice] = Field(default_factory=list)


class ConfirmedQueryContext(BaseModel):
    intent: RouterIntentType | None = None
    team: str | None = None
    function: str | None = None
    position: str | None = None
    branch: str | None = None
    branches: list[str] = Field(default_factory=list)
    performance_level: str | None = None
    metric_id: str | None = None
    metric_display_name: str | None = None
    periods: list[str] = Field(default_factory=list)
    comparison_type: Literal["period", "branch", "team", "none"] | None = "none"
    ranking_direction: Literal["best", "worst"] = "best"
    single_person: bool = False
    last_subject_employee_id: str | None = None
    last_subject_employee_name: str | None = None
    last_operation_kind: str | None = None
    pending_clarification_code: ClarificationCodeType | None = None
    pending_clarification_choices: list[ClarificationChoice] = Field(default_factory=list)
    inherited_filters: list[str] = Field(default_factory=list)


class StructuredQueryPlan(BaseModel):
    intent: RouterIntentType = "actual_vs_target"
    requested_parts: list[str] = Field(default_factory=list)
    team: str | None = None
    function: str | None = None
    position: str | None = None
    branch: str | None = None
    compare_branch: str | None = None
    branches: list[str] = Field(default_factory=list)
    performance_level: str | None = None
    metric: str | None = None
    periods: list[str] = Field(default_factory=list)
    ranking_direction: Literal["best", "worst"] = "best"
    single_person: bool = False
    employee_id: str | None = None
    employee_name: str | None = None
    employee_placeholder: str | None = None
    turn_kind_v2: TurnKindV2 = "analytical"
    operation_kind_v2: OperationKindV2 | None = None
    clarification_code: ClarificationCodeType = "NONE"
    asks_decisions: bool = False


class TypedMetricEvidence(BaseModel):
    metric_id: str
    kpi_key: str
    display_name: str
    team: str
    position: str | None = None
    performance_level: str = "Employee"
    branch: str = "all"
    period: str
    actual: float | None = None
    target: float | None = None
    actual_display: str
    target_display: str
    achievement_percent: float | None = None
    weight_percent: float = 0.0
    unit: str = "%"
    direction: str = "higher_better"
    contributes_to_score: bool = True
    tracking_only_note: str | None = None
    sample_size: int = 0
    source_link: str
    scoring_basis_status: str = "unchanged"
    scoring_basis_note: str | None = None


class SessionFilterContext(BaseModel):
    function: str | None = Field(default="Call Center")
    team: str | None = None
    position: str | None = None
    branch: str | None = None
    region: str | None = None
    performance_level: str | None = None
    month: str | None = None
    year: int | None = Field(default=None, ge=2000, le=2100)
    employee_id: str | None = None
    last_confirmed_query: ConfirmedQueryContext | None = None


class AiChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)


class AiChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    session_state: SessionFilterContext = Field(default_factory=SessionFilterContext)
    history: list[AiChatMessage] = Field(default_factory=list, max_length=12)
    provider_override: Literal["auto", "gemini", "openai", "local_ollama", "deterministic"] | None = "auto"
    answer_detail: Literal["auto", "brief", "details"] | None = "auto"
    conversation_id: str | None = Field(default=None, max_length=100)
    client_request_id: str | None = Field(default=None, max_length=100)
    context_version: int | None = Field(default=None, ge=0)
    clarification_choice_id: str | None = Field(default=None, max_length=120)


class AiBarItem(BaseModel):
    label: str
    value: float
    display_value: str
    target_value: float | None = None
    secondary_label: str | None = None
    severity: Literal["critical", "warning", "good", "neutral"] = "neutral"
    color: str | None = None


class AiEntityListItem(BaseModel):
    id: str
    title: str
    subtitle: str
    badge_text: str | None = None
    severity: Literal["critical", "warning", "good", "info"] = "warning"
    metric_value: str | None = None
    route_link: str | None = None


class AiKpiTableRow(BaseModel):
    kpi_key: str
    kpi_label: str
    weight_percent: float
    actual_display: str
    target_display: str
    achievement_percent: float | None = None
    direction: str = "higher_better"
    people_below_target: int = 0
    status: Literal["critical", "warning", "good", "neutral", "info"] = "neutral"
    unit: str | None = None
    contributes_to_score: bool = True
    tracking_only_badge: str | None = None


class AiDecisionItem(BaseModel):
    id: str
    priority: Literal["immediate", "high", "coaching", "strategic"] = "high"
    priority_label: str = "High Priority"
    title: str
    rationale: str
    expected_impact: str
    target_label: str
    route_link: str | None = None
    cta_label: str | None = None


class AiTrendPoint(BaseModel):
    month: str
    year: int = 2026
    period_label: str
    score: float
    target: float = 100.0
    grade: str | None = None


class AiSpotlightMetricTile(BaseModel):
    label: str
    value: str
    sublabel: str | None = None
    tone: Literal["neutral", "good", "warning", "critical"] = "neutral"


class AiSpotlightMetadata(BaseModel):
    kicker: str = "EXECUTIVE SPOTLIGHT"
    entity_name: str
    entity_id: str | None = None
    team: str
    rank_label: str | None = None
    score: float
    grade: Literal["A", "B", "C", "D", "E"] = "B"
    change_vs_prev: float | None = None
    previous_month_label: str = "August"
    six_month_delta: float | None = None
    target: float = 100.0
    headline_note: str | None = None
    tiles: list[AiSpotlightMetricTile] = Field(default_factory=list)
    kpi_chips: list[AiKpiTableRow] = Field(default_factory=list)
    trend_points: list[AiTrendPoint] = Field(default_factory=list)


class StructuredVisualCard(BaseModel):
    card_type: Literal[
        "horizontal_bar",
        "entity_list",
        "kpi_table",
        "guardrail_notice",
        "decision_playbook",
        "trend_spotlight",
    ]
    title: str
    subtitle: str | None = None
    bars: list[AiBarItem] = Field(default_factory=list)
    items: list[AiEntityListItem] = Field(default_factory=list)
    kpi_rows: list[AiKpiTableRow] = Field(default_factory=list)
    decisions: list[AiDecisionItem] = Field(default_factory=list)
    spotlight: AiSpotlightMetadata | None = None
    notice_text: str | None = None


class SourceCitationPill(BaseModel):
    label: str
    category: Literal["period", "scope", "branch", "metric", "basis", "policy"] = "scope"
    warning: bool = False


class DeepLinkCta(BaseModel):
    label: str
    route: str
    icon_key: Literal["insights", "team", "employee", "planning", "actions", "bsc"] = "insights"


class EvidenceItemV2(BaseModel):
    operation_id: str
    outcome: Literal["ok", "empty", "restricted", "unavailable", "unverified_capability"] = "ok"
    scope: QueryScopeV2 = Field(default_factory=QueryScopeV2)
    metric_id: str | None = None
    metric_display_name: str | None = None
    value_kind: str | None = None
    unit: str | None = None
    headline_value: float | str | None = None
    headline_display: str | None = None
    target_value: float | None = None
    target_display: str | None = None
    achievement_percent: float | None = None
    weight_percent: float | None = None
    contributes_to_score: bool = True
    rows: list[dict[str, Any]] = Field(default_factory=list)
    ties: list[str] = Field(default_factory=list)
    record_count: int = 0
    missing_count: int = 0
    publication_id: str | None = None
    revision_id: str | None = None
    aggregation_version: str = "v2"
    source_link: DeepLinkCta | None = None
    notes: list[str] = Field(default_factory=list)


class AiToolCallRecord(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    records_evaluated: int = 0


class AiTurnTimingBreakdown(BaseModel):
    resolution_ms: float = 0.0
    provider_ms: float = 0.0
    database_ms: float = 0.0
    render_ms: float = 0.0
    trace_ms: float = 0.0
    total_ms: float = 0.0


class AiProviderUsageMetrics(BaseModel):
    router_mode: Literal["legacy", "shadow", "hybrid"] = "hybrid"
    route_used: str = "local_rules"
    provider_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    fallback_outcome: str = "none"
    shadow_plan: dict[str, Any] | None = None


class AiChatResponsePayload(BaseModel):
    trace_id: str
    conversation_id: str | None = None
    turn_id: str | None = None
    context_version: int = 0
    outcome: TurnOutcomeType = "answer"
    answer_detail: Literal["brief", "details"] = "details"
    headline: str
    narrative_bullets: list[str] = Field(default_factory=list)
    visual_cards: list[StructuredVisualCard] = Field(default_factory=list)
    citations: list[SourceCitationPill] = Field(default_factory=list)
    deep_links: list[DeepLinkCta] = Field(default_factory=list)
    primary_source_link: DeepLinkCta | None = None
    suggested_followups: list[str] = Field(default_factory=list)
    resolved_session_state: SessionFilterContext
    scope_banner: str | None = None
    inherited_filters: list[str] = Field(default_factory=list)
    clarification: AiClarificationPrompt | None = None
    structured_query: StructuredQueryPlan | None = None
    validated_plan_v2: ValidatedQueryPlanV2 | None = None
    typed_evidence: list[TypedMetricEvidence] = Field(default_factory=list)
    evidence_envelope_v2: list[EvidenceItemV2] = Field(default_factory=list)
    domain_guardrail_notes: list[str] = Field(default_factory=list)
    tool_calls: list[AiToolCallRecord] = Field(default_factory=list)
    provider_used: str = "deterministic"
    model_used: str = "pms-deterministic-v1"
    latency_ms: int = 0
    timings: AiTurnTimingBreakdown = Field(default_factory=AiTurnTimingBreakdown)
    provider_usage: AiProviderUsageMetrics = Field(default_factory=AiProviderUsageMetrics)
    basis_warning: str | None = None
    cache_hit: bool = False


class AiChatResponse(BaseModel):
    success: bool = True
    message: str = "AI analytical response generated"
    data: AiChatResponsePayload


class AiWatchingAlertItem(BaseModel):
    id: str
    title: str
    subtitle: str
    severity: Literal["critical", "warning", "info"] = "warning"
    badge_text: str | None = None
    prompt_to_ask: str
    deep_link: str | None = None


class AiGuardrailItem(BaseModel):
    label: str
    description: str
    verified: bool = True


class AiStarterPrompt(BaseModel):
    id: str
    label: str
    subtitle: str | None = None
    badge: str | None = None
    prompt: str
    category: Literal["team", "kpi", "people", "branch", "governance"] = "team"
    icon_key: Literal["alert", "users", "chart", "shield"] = "chart"


class AiEligibleTeamItem(BaseModel):
    value: str
    label: str
    function: str
    badge: str | None = None


class AiWatchingPayload(BaseModel):
    resolved_session_state: SessionFilterContext
    alerts: list[AiWatchingAlertItem] = Field(default_factory=list)
    guardrails: list[AiGuardrailItem] = Field(default_factory=list)
    starter_prompts: list[AiStarterPrompt] = Field(default_factory=list)
    eligible_teams: list[AiEligibleTeamItem] = Field(default_factory=list)
    eligible_functions: list[str] = Field(default_factory=list)
    eligible_branches: list[str] = Field(default_factory=list)
    eligible_levels: list[str] = Field(default_factory=list)
    summary_score: float | None = None
    summary_score_change: float | None = None
    measured_records: int = 0


class AiWatchingResponse(BaseModel):
    success: bool = True
    message: str = "AI watching workspace loaded"
    data: AiWatchingPayload


class AiFeedbackRequest(BaseModel):
    trace_id: str = Field(..., min_length=1, max_length=100)
    rating: Literal["up", "down"]
    reason: str | None = Field(default=None, max_length=120)
    reviewer_verified: bool | None = None


class AiFeedbackResponse(BaseModel):
    success: bool = True
    message: str = "Feedback recorded"
    trace_id: str
    rating: Literal["up", "down"]
    is_distillation_eligible: bool
    reviewer_verified: bool = False


class AiDistillationRecord(BaseModel):
    trace_id: str
    created_at: str
    role: str
    router_training_pair: dict[str, Any]
    narrative_training_pair: dict[str, Any] | None = None
    provider_name: str
    model_name: str
    reviewer_verified: bool = False


class AiDistillationExportResponse(BaseModel):
    success: bool = True
    total_exported: int
    records: list[AiDistillationRecord] = Field(default_factory=list)


class AiConversationCreateRequest(BaseModel):
    session_state: SessionFilterContext = Field(default_factory=SessionFilterContext)


class AiConversationContextPayload(BaseModel):
    conversation_id: str
    owner_user_id: str
    status: Literal["active", "archived", "deleted"] = "active"
    context_version: int = 0
    confirmed_context: ConfirmedQueryContext = Field(default_factory=ConfirmedQueryContext)
    pending_clarification: AiClarificationPrompt | None = None
    last_subject_employee_id: str | None = None
    last_subject_employee_name: str | None = None
    last_operation_kind: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class AiConversationResponse(BaseModel):
    success: bool = True
    message: str = "Conversation loaded"
    data: AiConversationContextPayload


class AiCatalogMetricItem(BaseModel):
    metric_id: str
    kpi_key: str
    display_name: str
    team: str
    function: str
    position: str | None = None
    performance_level: str = "Employee"
    value_kind: MetricValueKindType = "rate"
    unit: str = "%"
    storage_scale: str = "ratio_0_1"
    direction: str = "higher_better"
    aggregation: str = "ratio_of_sums"
    weight_percent: float = 0.0
    contributes_to_score: bool = True
    available_operations: list[str] = Field(default_factory=list)
    status: Literal["verified", "partial", "unverified", "unavailable"] = "verified"


class AiCatalogPayload(BaseModel):
    eligible_teams: list[AiEligibleTeamItem] = Field(default_factory=list)
    eligible_functions: list[str] = Field(default_factory=list)
    eligible_branches: list[str] = Field(default_factory=list)
    eligible_levels: list[str] = Field(default_factory=list)
    metrics: list[AiCatalogMetricItem] = Field(default_factory=list)
    capabilities: list[dict[str, Any]] = Field(default_factory=list)


class AiCatalogResponse(BaseModel):
    success: bool = True
    message: str = "Authorized AI catalog loaded"
    data: AiCatalogPayload


class AiTraceReviewRequest(BaseModel):
    reviewer_verified: bool = True
    notes: str | None = Field(default=None, max_length=240)


class AiTraceReviewResponse(BaseModel):
    success: bool = True
    message: str = "Trace review updated"
    trace_id: str
    reviewer_verified: bool
    reviewer_id: str
    reviewed_at: str
    is_distillation_eligible: bool
