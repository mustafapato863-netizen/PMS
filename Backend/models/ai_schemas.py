from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from services.ai.evidence import CatalogEvidence, publish_evidence


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
    "person_worst_period",
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
    resolution_source: Literal["local_rules", "local_classifier", "local_model_router", "gemini_router", "clarification_choice"] = "local_rules"
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
    region: str | None = None
    performance_level: str | None = None
    metric_id: str | None = None
    metric_display_name: str | None = None
    candidate_metrics: list[str] = Field(default_factory=list)
    periods: list[str] = Field(default_factory=list)
    comparison_type: Literal["period", "branch", "team", "none"] | None = "none"
    ranking_direction: Literal["best", "worst"] = "best"
    single_person: bool = False
    last_subject_employee_id: str | None = None
    last_subject_employee_name: str | None = None
    candidate_employees: list[dict[str, str]] = Field(default_factory=list)
    last_operation_kind: str | None = None
    pending_clarification_code: ClarificationCodeType | None = None
    pending_clarification_choices: list[ClarificationChoice] = Field(default_factory=list)
    inherited_filters: list[str] = Field(default_factory=list)
    prior_ranking_intent: bool = False


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
    model_led_tool_call: dict | None = None
    model_led_tool_calls: list[dict] = Field(default_factory=list, max_length=2)
    model_led_direct_response: str | None = None
    model_led_clarification: dict | None = None


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
    actual_display: str = ""
    target_display: str | None = None
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
    employee_id: str | None = None
    employee_name: str | None = None


class PageContextV1(BaseModel):
    page_id: str | None = Field(default=None, max_length=80)
    route_id: str | None = Field(default=None, max_length=240)
    function_id: str | None = Field(default=None, max_length=80)
    team_id: str | None = Field(default=None, max_length=120)
    position_id: str | None = Field(default=None, max_length=120)
    employee_id: str | None = Field(default=None, max_length=80)
    performance_level: str | None = Field(default=None, max_length=40)
    region: str | None = Field(default=None, max_length=40)
    branch: str | None = Field(default=None, max_length=40)
    period: str | None = Field(default=None, max_length=40)
    month: str | None = Field(default=None, max_length=30)
    year: int | None = Field(default=None, ge=2000, le=2100)
    selected_entity_type: Literal["team", "employee", "metric", "branch", "position"] | None = None
    selected_entity_id: str | None = Field(default=None, max_length=120)
    selected_metric_id: str | None = Field(default=None, max_length=120)
    selected_visual_id: str | None = Field(default=None, max_length=120)
    is_fallback_data: bool = False
    client_context_version: int = Field(default=0, ge=0)


ContextualCapabilityMode = Literal[
    "greeting",
    "capabilities_help",
    "page_help",
    "navigation",
    "performance_query",
    "clarification",
    "explain_previous",
    "off_topic",
    "proposal",
    "unsupported",
]

ConversationOriginType = Literal["workspace", "page_assistant", "legacy"]
ConversationOriginInputType = Literal["workspace", "page_assistant"]

FeedbackCategoryType = Literal[
    "helpful",
    "wrong_data",
    "misunderstood_question",
    "lost_context",
    "too_long",
    "incorrect_answer",
    "incorrect_scope",
    "incomplete_response",
    "poor_suggestion",
    "other",
    "incorrect_kpi_interpretation",
    "unsupported_recommendation",
    "irrelevant_action",
    "missing_context",
    "inadequate_explanation",
    "unclear_uncertainty_statement",
    "provider_or_technical_failure",
    "good_quality_recommendation",
]

FeedbackSurfaceType = Literal["workspace_chat", "corrective_action_pilot"]
FeedbackReviewDecisionType = Literal["approved", "rejected"]
FeedbackReviewStatusType = Literal["pending", "approved", "rejected"]


class AiPageHelpSection(BaseModel):
    page_id: str
    page_title: str
    summary: str
    key_elements: list[str] = Field(default_factory=list)
    available_actions: list[str] = Field(default_factory=list)
    metric_explanation: str | None = None
    fallback_data_warning: str | None = None


class AiNavigationTarget(BaseModel):
    id: str
    label: str
    route: str
    description: str
    icon_key: Literal["insights", "team", "employee", "planning", "actions", "bsc", "presentation"] = "insights"


class AiCorrectiveActionProposal(BaseModel):
    proposal_id: str
    title: str
    scope_summary: str
    team: str
    function: str | None = None
    position: str | None = None
    performance_level: str = "Employee"
    branch_key: str | None = None
    period: str
    month: str
    year: int
    employee_id: str | None = None
    employee_name: str | None = None
    metric_id: str
    linked_kpi_key: str
    metric_display_name: str
    actual_display: str
    target_display: str
    gap_display: str
    sample_size: int = 0
    observed_facts: list[str] = Field(default_factory=list)
    hypothesis: str | None = None
    suggested_steps: list[str] = Field(default_factory=list)
    success_measure: str
    action_type: Literal["Coaching", "Training", "PIP", "Monitor", "Warning", "Reward", "Promotion"] = "Coaching"
    priority: Literal["Low", "Medium", "High"] = "Medium"
    proposed_action_text: str
    proposed_root_cause_note: str
    evidence_revision: str
    source_link: str | None = None
    can_user_create_action: bool = False
    persisted_status_on_save: Literal["Open"] = "Open"
    assignable_owners: list[dict[str, str]] = Field(default_factory=list)


class AiCorrectiveActionConfirmRequest(BaseModel):
    proposal_id: str = Field(..., min_length=1, max_length=120)
    team: str = Field(..., min_length=1, max_length=120)
    month: str = Field(..., min_length=1, max_length=30)
    year: int = Field(..., ge=2000, le=2100)
    action_type: Literal["Coaching", "Training", "PIP", "Monitor", "Warning", "Reward", "Promotion", "Team Action"] = "Coaching"
    action_text: str = Field(..., min_length=3, max_length=1500)
    root_cause_note: str = Field(default="", max_length=1500)
    employee_id: str | None = Field(default=None, max_length=80)
    priority: Literal["Low", "Medium", "High"] | None = None
    due_date: str | None = Field(default=None, max_length=30)
    owner_user_id: str | None = Field(default=None, max_length=80)
    linked_kpi_key: str | None = Field(default=None, max_length=100)
    evidence_revision: str = Field(..., min_length=1, max_length=160)
    is_fallback_data: bool = False
    trace_id: str | None = Field(default=None, max_length=100)


class AiCorrectiveActionConfirmResponse(BaseModel):
    success: bool = True
    message: str = "Corrective action created with status Open"
    persisted_status: Literal["Open"] = "Open"
    action_scope: Literal["employee", "team"] = "employee"
    action: dict[str, Any]


# ---------------------------------------------------------------------------
# Corrective-action suggestion drafter (#98). Read-only: a suggestion is an
# unapproved draft; saving goes through the existing corrective-action workflow.
# ---------------------------------------------------------------------------

CorrectiveActionSuggestionOutcome = Literal[
    "suggested",
    "insufficient_evidence",
    "model_unavailable",
    # The model answered, but the answer was malformed or failed validation
    # against the evidence. No draft is returned and nothing is substituted.
    "draft_rejected",
]

# Who produced ``draft``. ``"deterministic"`` is part of the shared provider
# vocabulary but this endpoint never emits it: it does not substitute a static
# draft when the model is unavailable or its answer is rejected.
CorrectiveActionSuggestionProvider = Literal["cloudflare", "gemini", "deterministic", "none"]

# A draft may only propose a non-disciplinary action type. PIP, Warning,
# Reward and Promotion remain human decisions in the existing workflow.
CorrectiveActionDraftType = Literal["Coaching", "Training", "Monitor"]


class AiCorrectiveActionSuggestionRequest(BaseModel):
    model_config = {"extra": "forbid"}

    team: str = Field(..., min_length=1, max_length=120)
    month: str = Field(..., min_length=1, max_length=30)
    year: int = Field(..., ge=2000, le=2100)
    performance_level: str = Field(default="Employee", min_length=1, max_length=40)
    employee_id: str | None = Field(default=None, min_length=1, max_length=80)
    linked_kpi_key: str | None = Field(default=None, min_length=1, max_length=100)


class AiCorrectiveActionSuggestionPeriod(BaseModel):
    month: str
    year: int


ObservationStatus = Literal["verified", "recorded_zero", "unverified_zero", "missing"]


class AiCorrectiveActionSuggestionContext(BaseModel):
    subject: Literal["employee", "team"]
    employee_id: str | None = None
    employee_name: str | None = None
    country: str | None = None
    function: str | None = None
    team: str
    position: str | None = None
    period: AiCorrectiveActionSuggestionPeriod
    performance_level: str
    scoring_basis: str | None = None
    linked_kpi_key: str | None = None
    team_headcount: int | None = None


class AiCorrectiveActionSuggestionKpiEvidence(BaseModel):
    """One stored KPI row, as read. ``None`` means missing; ``0.0`` is a real zero."""

    employee_id: str | None = None
    kpi_key: str
    display_name: str
    actual: float | None = None
    target: float | None = None
    unit: str | None = None
    direction: str | None = None
    weight: float | None = None
    achievement_ratio: float | None = None
    achievement_percent: float | None = None
    contributes_to_score: bool = True
    status: Literal["below_target", "at_or_above_target", "unknown"] = "unknown"
    observation_status: ObservationStatus = "verified"
    previous_actual: float | None = None
    previous_period: str | None = None
    projected_agent_score_lift: float | None = None


class AiCorrectiveActionSuggestionTrendSummary(BaseModel):
    measured_periods: int = 0
    current_score: float | None = None
    previous_score: float | None = None
    previous_period: str | None = None
    previous_is_adjacent: bool = True
    missing_intermediate_periods: list[str] = Field(default_factory=list)
    window_start_period: str | None = None
    window_start_score: float | None = None
    window_delta: float | None = None
    score_delta: float | None = None
    score_direction: str = "single_period"
    kpi_trends: dict[str, dict[str, Any]] = Field(default_factory=dict)
    weak_kpis: list[dict[str, Any]] = Field(default_factory=list)


class AiCorrectiveActionSuggestionPriorAction(BaseModel):
    action_type: str | None = None
    status: str | None = None
    linked_kpi_key: str | None = None
    period: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None


class AiCorrectiveActionSuggestionDraft(BaseModel):
    """Unapproved draft. Facts and uncertainty come from PMS evidence; wording is built
    from validated structured action choices or closed-vocabulary steps."""

    title: str
    focus_kpi_key: str
    focus_kpi_name: str
    action_type: CorrectiveActionDraftType
    action_choice: str | None = None
    follow_up_interval: str | None = None
    official_target_label: str | None = None
    action_milestone_note: str | None = None
    # Built in code from the evidence ledger; the model cannot alter it.
    measured_issue: str
    measured_issue_source: Literal["pms_evidence"] = "pms_evidence"
    # Validated steps (built from validated structured choice or closed-vocabulary validation).
    recommended_steps: list[str] = Field(default_factory=list, min_length=1, max_length=3)
    recommended_steps_source: Literal["cloudflare", "gemini"] = "cloudflare"
    # Built in code: what the evidence does not show.
    uncertainty: str
    uncertainty_source: Literal["pms_evidence"] = "pms_evidence"
    approval_status: Literal["unapproved_draft"] = "unapproved_draft"
    responsible_role: str | None = None
    recommended_follow_up: str | None = None
    observation_status: ObservationStatus | None = None
    formatted_next_step: str | None = None


class AiCorrectiveActionSuggestionPayload(BaseModel):
    outcome: CorrectiveActionSuggestionOutcome
    provider_used: CorrectiveActionSuggestionProvider = "none"
    model_called: bool = False
    model_version: str | None = None
    fallback_reason: str | None = None
    validation_errors: list[str] = Field(default_factory=list)
    repair_attempted: bool = False
    context: AiCorrectiveActionSuggestionContext
    focus_kpi_key: str | None = None
    cohort_in_scope_count: int | None = None
    cohort_measured_count: int | None = None
    cohort_unmeasured_count: int | None = None
    cohort_below_target_count: int | None = None
    cohort_coverage_label: str | None = None
    official_target_label: str | None = None
    measured_actual_label: str | None = None
    # Deterministic statements built from the evidence ledger, never by the model.
    measured_facts: list[str] = Field(default_factory=list)
    # Deterministic evidence caveats (always includes that the cause is not established).
    evidence_limitations: list[str] = Field(default_factory=list)
    supporting_kpis: list[AiCorrectiveActionSuggestionKpiEvidence] = Field(default_factory=list)
    supporting_kpis_truncated: bool = False
    prior_actions: list[AiCorrectiveActionSuggestionPriorAction] = Field(default_factory=list)
    trend_summary: AiCorrectiveActionSuggestionTrendSummary | None = None
    insufficient_evidence_reasons: list[str] = Field(default_factory=list)
    draft: AiCorrectiveActionSuggestionDraft | None = None
    # When evidence is sufficient but the AI provider failed/was rejected, PMS supplies
    # an explicit evidence-based next step without asserting AI approval.
    evidence_next_step: str | None = None
    evidence_next_step_label: str | None = None
    evidence_next_step_role: str | None = None
    evidence_next_step_follow_up: str | None = None
    evidence_next_step_action_type: CorrectiveActionDraftType | None = None
    evidence_next_step_source: Literal["pms_evidence"] | None = None
    model_latency_ms: float | None = None
    read_only: Literal[True] = True
    requires_human_confirmation: Literal[True] = True

    @model_validator(mode="after")
    def _draft_matches_outcome(self) -> "AiCorrectiveActionSuggestionPayload":
        if self.outcome == "suggested":
            if self.draft is None or self.provider_used not in ("cloudflare", "gemini"):
                raise ValueError("a suggested outcome requires a validated model draft")
        elif self.draft is not None:
            raise ValueError("only a suggested outcome may carry a draft")
        return self


KpiEvidenceItem = AiCorrectiveActionSuggestionKpiEvidence
AiKpiEvidence = AiCorrectiveActionSuggestionKpiEvidence
AiSuggestionContext = AiCorrectiveActionSuggestionContext
TrendSummary = AiCorrectiveActionSuggestionTrendSummary
AiTrendSummary = AiCorrectiveActionSuggestionTrendSummary


class AiCorrectiveActionSuggestionResponse(BaseModel):
    success: bool = True
    message: str
    data: AiCorrectiveActionSuggestionPayload


class SessionFilterContext(BaseModel):
    function: str | None = None
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
    page_context: PageContextV1 | None = None
    capability_hint: Literal["auto", "page_help", "navigation", "performance_query", "proposal"] | None = "auto"
    history: list[AiChatMessage] = Field(default_factory=list, max_length=12)
    provider_override: Literal["auto", "gemini", "deterministic"] | None = "auto"
    answer_detail: Literal["auto", "brief", "details"] | None = "auto"
    conversation_id: str | None = Field(default=None, max_length=100)
    client_request_id: str | None = Field(default=None, max_length=100)
    context_version: int | None = Field(default=None, ge=0)
    clarification_choice_id: str | None = Field(default=None, max_length=120)
    variation_seed: int | None = Field(default=None, ge=0, le=50)
    origin: ConversationOriginInputType | None = None


class AiBarItem(BaseModel):
    label: str
    # Null means "no recorded value" (e.g. a branch with no published
    # bookings/score) — never a fake 0.0. Consumers must render a null bar
    # with no fill, using display_value ("Unavailable") as the label.
    value: float | None
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
    neurons: int = 0
    estimated_cost_usd: float = 0.0
    cost_status: Literal["measured_usd", "measured_neurons", "unknown", "not_applicable"] = "not_applicable"
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
    detail_bullets: list[str] = Field(default_factory=list)
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
    answer_source: str = "deterministic"
    latency_ms: int = 0
    timings: AiTurnTimingBreakdown = Field(default_factory=AiTurnTimingBreakdown)
    provider_usage: AiProviderUsageMetrics = Field(default_factory=AiProviderUsageMetrics)
    basis_warning: str | None = None
    cache_hit: bool = False
    capability_mode: ContextualCapabilityMode = "performance_query"
    effective_context_label: str | None = None
    page_help: AiPageHelpSection | None = None
    navigation_targets: list[AiNavigationTarget] = Field(default_factory=list)
    action_proposal: AiCorrectiveActionProposal | None = None


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
    regions: list[str] = Field(default_factory=list)


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
    category: FeedbackCategoryType | None = None
    reason: str | None = Field(default=None, max_length=120)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    # Accepted for legacy clients; review is performed only through the Admin review endpoint.
    reviewer_verified: bool | None = None


class AiFeedbackResponse(BaseModel):
    success: bool = True
    message: str = "Feedback recorded"
    trace_id: str
    rating: Literal["up", "down"]
    category: FeedbackCategoryType | None = None
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
    origin: ConversationOriginInputType = "workspace"


class AiConversationContextPayload(BaseModel):
    conversation_id: str
    owner_user_id: str
    origin: ConversationOriginType = "workspace"
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


class AiConversationSummaryItem(BaseModel):
    conversation_id: str
    title: str | None = None
    origin: ConversationOriginType = "workspace"
    created_at: str | None = None
    updated_at: str | None = None
    turn_count: int = 0
    last_outcome: str | None = None
    last_scope_banner: str | None = None
    last_period: str | None = None
    has_restricted_turns: bool = False
    context_version: int = 0


class AiConversationListResponse(BaseModel):
    success: bool = True
    message: str = "Conversations loaded"
    conversations: list[AiConversationSummaryItem] = Field(default_factory=list)


class AiConversationRetrySettings(BaseModel):
    session_state: SessionFilterContext = Field(default_factory=SessionFilterContext)
    clarification_choice_id: str | None = None
    answer_detail: Literal["auto", "brief", "details"] | None = None
    variation_seed: int | None = None


class AiConversationTurnDetail(BaseModel):
    turn_id: str
    turn_index: int
    client_request_id: str | None = None
    retry_settings: AiConversationRetrySettings | None = None
    status: Literal["pending", "completed", "failed", "restricted", "superseded"]
    user_prompt: str
    error_message: str | None = None
    scope_used: str | None = None
    period_used: str | None = None
    created_at: str | None = None
    completed_at: str | None = None
    response: AiChatResponsePayload | None = None


class AiConversationDetailPayload(BaseModel):
    conversation_id: str
    owner_user_id: str
    title: str | None = None
    origin: ConversationOriginType = "workspace"
    status: Literal["active", "archived", "deleted"] = "active"
    context_version: int = 0
    confirmed_context: ConfirmedQueryContext = Field(default_factory=ConfirmedQueryContext)
    pending_clarification: AiClarificationPrompt | None = None
    has_restricted_turns: bool = False
    created_at: str | None = None
    updated_at: str | None = None
    turns: list[AiConversationTurnDetail] = Field(default_factory=list)


class AiConversationDetailResponse(BaseModel):
    success: bool = True
    message: str = "Conversation loaded"
    data: AiConversationDetailPayload


EvidenceState = Literal["verified", "verified_no_data", "partial", "blocked", "not_applicable"]


class AiCatalogEvidence(BaseModel):
    tests: list[str] = Field(default_factory=list)
    fixture_or_source_version: str = ""
    reviewed_on: str = ""
    reviewer: str = "pending"


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
    status: EvidenceState = "blocked"
    evidence: AiCatalogEvidence = Field(default_factory=AiCatalogEvidence)
    evidence_passes: bool = False

    @model_validator(mode="after")
    def incomplete_evidence_is_not_a_pass(self) -> "AiCatalogMetricItem":
        state, passes = publish_evidence(
            CatalogEvidence(
                state=self.status,
                tests=tuple(self.evidence.tests),
                fixture_or_source_version=self.evidence.fixture_or_source_version,
                reviewed_on=self.evidence.reviewed_on,
                reviewer=self.evidence.reviewer,
            )
        )
        self.status = state  # type: ignore[assignment]
        self.evidence_passes = passes
        return self


class AiCatalogPayload(BaseModel):
    eligible_teams: list[AiEligibleTeamItem] = Field(default_factory=list)
    eligible_functions: list[str] = Field(default_factory=list)
    eligible_regions: list[str] = Field(default_factory=list)
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
    decision: FeedbackReviewDecisionType | None = None
    notes: str | None = Field(default=None, max_length=240)
    proposed_action: str | None = Field(default=None, max_length=240)

    @model_validator(mode="after")
    def _sync_decision_and_verified(self) -> "AiTraceReviewRequest":
        if "decision" in self.model_fields_set and self.decision is not None:
            expected_verified = self.decision == "approved"
            if "reviewer_verified" in self.model_fields_set and self.reviewer_verified != expected_verified:
                raise ValueError("decision and reviewer_verified conflict")
            self.reviewer_verified = expected_verified
        else:
            self.decision = "approved" if self.reviewer_verified else "rejected"
        return self


class AiTraceReviewResponse(BaseModel):
    success: bool = True
    message: str = "Trace review updated"
    trace_id: str
    reviewer_verified: bool
    reviewer_id: str
    reviewed_at: str
    is_distillation_eligible: bool
    decision: FeedbackReviewDecisionType | None = None
    review_status: FeedbackReviewStatusType | None = None
    proposed_action: str | None = None


class AiPilotFeedbackRequest(BaseModel):
    trace_id: str | None = Field(default=None, max_length=100)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    surface: FeedbackSurfaceType = "corrective_action_pilot"
    rating: Literal["up", "down"]
    reason_tag: FeedbackCategoryType | None = None
    comment: str | None = Field(default=None, max_length=500)
    candidate_sha: str | None = Field(default=None, max_length=64)
    model_version: str | None = Field(default=None, max_length=120)
    provider_name: str | None = Field(default=None, max_length=60)
    fallback_reason: str | None = Field(default=None, max_length=120)
    operation_family: str | None = Field(default=None, max_length=80)
    scope_team: str | None = Field(default=None, max_length=120)
    scope_country: str | None = Field(default=None, max_length=80)
    performance_level: str | None = Field(default=None, max_length=40)
    evidence_ids: list[str] = Field(default_factory=list, max_length=50)


class AiPilotFeedbackResponse(BaseModel):
    success: bool = True
    message: str = "Feedback recorded for administrator review"
    trace_id: str
    surface: FeedbackSurfaceType
    rating: Literal["up", "down"]
    reason_tag: FeedbackCategoryType | None = None
    review_status: FeedbackReviewStatusType = "pending"
    reviewer_verified: bool = False
    pii_quarantined: bool = False


class AiFeedbackTraceSample(BaseModel):
    trace_id: str
    prompt_redacted: str
    intent: str
    operation_kind: str | None = None
    tool_choice: str | None = None
    rating: str | None = None
    failure_category: str = "unspecified"
    feedback_reason: str | None = None
    review_status: str = "pending"
    reviewer_verified: bool = False
    created_at: str | None = None


class AiFeedbackClusterItem(BaseModel):
    surface: str
    fallback_reason: str
    operation_family: str
    scope_team: str
    reason_tag: str
    intent: str = "unspecified"
    failure_category: str = "unspecified"
    total_count: int
    up_count: int = 0
    down_count: int = 0
    pending_count: int = 0
    approved_count: int = 0
    rejected_count: int = 0
    traces: list[AiFeedbackTraceSample] = Field(default_factory=list)


class AiFeedbackClustersResponse(BaseModel):
    success: bool = True
    total_traces: int
    clusters: list[AiFeedbackClusterItem] = Field(default_factory=list)


class AiApprovePatternRequest(BaseModel):
    corrected_pattern_prompt: str | None = Field(default=None, max_length=300)
    intent: str = Field(..., min_length=1, max_length=64)
    operation_kind: str | None = Field(default=None, max_length=64)
    requested_parts: list[str] | None = Field(default=None, max_length=10)
    tool_choice: str | None = Field(default=None, max_length=80)
    metric_hint: str | None = Field(default=None, max_length=120)
    failure_category: str | None = Field(default=None, max_length=64)
    verified_against_pms: bool = False
    review_notes: str | None = Field(default=None, max_length=240)


class AiApprovedPatternItem(BaseModel):
    id: str
    source_trace_id: str | None = None
    normalized_pattern: str
    example_prompt_redacted: str
    intent: str
    operation_kind: str | None = None
    requested_parts: list[str] | None = None
    tool_choice: str | None = None
    metric_hint: str | None = None
    failure_category: str | None = None
    verified_against_pms: bool = False
    approved_by_user_id: str | None = None
    review_notes: str | None = None
    is_active: bool = True
    created_at: str | None = None


class AiApprovedPatternListResponse(BaseModel):
    success: bool = True
    patterns: list[AiApprovedPatternItem] = Field(default_factory=list)


class AiApprovePatternResponse(BaseModel):
    success: bool = True
    message: str = "Pattern verified and saved"
    pattern: AiApprovedPatternItem
    trace_review: AiTraceReviewResponse | None = None


class AiFeedbackPurgeRequest(BaseModel):
    retention_days: int | None = Field(default=None, ge=1, le=365)
    dry_run: bool = False


class AiFeedbackPurgeResponse(BaseModel):
    success: bool = True
    retention_days: int
    dry_run: bool
    matched_count: int
    purged_count: int
    cutoff_iso: str


class AiDeidentifiedExportItem(BaseModel):
    trace_id: str
    created_at: str
    surface: str
    rating: str | None = None
    reason_tag: str | None = None
    comment: str | None = None
    candidate_sha: str | None = None
    model_version: str | None = None
    provider_name: str
    fallback_reason: str | None = None
    operation_family: str | None = None
    scope_team: str | None = None
    scope_country: str | None = None
    performance_level: str | None = None
    cohort_size: int
    evidence_ids: list[str] = Field(default_factory=list)
    review_status: str
    proposed_action: str | None = None


class AiDeidentifiedExportBundleResponse(BaseModel):
    success: bool = True
    approved_only: bool = True
    min_cohort_size: int = 5
    exported_count: int
    blocked_small_cohort_count: int = 0
    blocked_pii_count: int = 0
    items: list[AiDeidentifiedExportItem] = Field(default_factory=list)


class AiDiagnosticsPayload(BaseModel):
    feature_enabled: bool
    pilot_role_restricted: bool = True
    model_configured_name: str
    model_version: str | None = None
    model_endpoint_configured: bool
    model_endpoint_host: str | None = None
    model_available: bool
    inference_verified: bool = False
    provider_status_code: Literal["configured", "credentials_present", "live_verified", "live_failed", "fallback_active", "unavailable"] = "unavailable"
    live_verified_at: str | None = None
    live_verification_latency_ms: float | None = None
    live_verification_error: str | None = None
    model_availability_reason: str
    router_mode: str
    intent_routing_enabled: bool
    synthesis_enabled: bool
    exploration_enabled: bool
    routing_provider: Literal["cloudflare", "gemini", "deterministic"] = "deterministic"
    synthesis_provider: Literal["cloudflare", "gemini", "deterministic"] = "deterministic"
    brief_default_enabled: bool
    conversation_state_enabled: bool
    provider_timeout_seconds: float
    recent_fallback_reason: str | None = None
    fallback_scope: str = "process_local"
    model_led_pilot_enabled: bool = False
    max_concurrent_requests: int = 8
    active_concurrent_requests: int = 0
    daily_user_request_limit: int = 0
    daily_user_token_limit: int = 0
    max_request_input_tokens: int = 8192
    router_timeout_seconds: float = 10.0
    synthesis_timeout_seconds: float = 15.0
    rejected_budget_requests: int = 0
    data_freshness: dict[str, Any] = Field(default_factory=dict)


class AiDiagnosticsResponse(BaseModel):
    success: bool = True
    message: str = "Admin AI diagnostics loaded"
    data: AiDiagnosticsPayload
