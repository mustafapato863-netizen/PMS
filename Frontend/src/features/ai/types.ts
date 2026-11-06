export type RouterIntentType =
  | 'current_value'
  | 'actual_vs_target'
  | 'compare_periods'
  | 'compare_branches'
  | 'compare_teams'
  | 'trend'
  | 'ranking'
  | 'score_drivers'
  | 'scorecard_structure'
  | 'corrective_actions'
  | 'clarify'
  | 'unsupported';

export type ClarificationCodeType =
  | 'NONE'
  | 'AMBIGUOUS_ABANDON_METRIC'
  | 'AMBIGUOUS_ATTENDANCE_DEFINITION'
  | 'AMBIGUOUS_TEAM_SCOPE'
  | 'AMBIGUOUS_KPI_SCOPE'
  | 'AMBIGUOUS_PERSON'
  | 'AMBIGUOUS_COUNT_VS_RATE'
  | 'MISSING_HR_JOIN_DATE'
  | 'MISSING_COMPARISON_PERIOD'
  | 'RESTRICTED_SCOPE_SUGGESTION'
  | 'UNAVAILABLE_PERIOD_SUGGESTION';

export type TurnOutcomeType =
  | 'answer'
  | 'clarification'
  | 'restricted_access'
  | 'unavailable_data'
  | 'unsupported_request';

export interface ClarificationChoice {
  id: string;
  label: string;
  description?: string | null;
  prompt_to_send: string;
  team?: string | null;
  position?: string | null;
  metric_id?: string | null;
  performance_level?: string | null;
  period?: string | null;
  branch?: string | null;
  employee_id?: string | null;
  employee_name?: string | null;
}

export interface AiClarificationPrompt {
  code: ClarificationCodeType;
  question: string;
  choices: ClarificationChoice[];
}

export interface ConfirmedQueryContext {
  intent?: RouterIntentType | null;
  team?: string | null;
  function?: string | null;
  position?: string | null;
  branch?: string | null;
  branches?: string[];
  performance_level?: string | null;
  metric_id?: string | null;
  metric_display_name?: string | null;
  periods?: string[];
  comparison_type?: 'period' | 'branch' | 'team' | 'none' | null;
  pending_clarification_code?: ClarificationCodeType | null;
  pending_clarification_choices?: ClarificationChoice[];
  last_subject_employee_id?: string | null;
  last_subject_employee_name?: string | null;
  last_operation_kind?: string | null;
  inherited_filters?: string[];
}

export interface StructuredQueryPlan {
  intent: RouterIntentType;
  requested_parts?: string[];
  team?: string | null;
  function?: string | null;
  position?: string | null;
  branch?: string | null;
  compare_branch?: string | null;
  performance_level?: string | null;
  metric?: string | null;
  periods: string[];
  ranking_direction: 'best' | 'worst';
  single_person: boolean;
  employee_placeholder?: string | null;
  clarification_code: ClarificationCodeType;
  asks_decisions: boolean;
}

export interface TypedMetricEvidence {
  metric_id: string;
  kpi_key: string;
  display_name: string;
  team: string;
  position?: string | null;
  performance_level: string;
  branch: string;
  period: string;
  actual?: number | null;
  target?: number | null;
  actual_display: string;
  target_display: string;
  achievement_percent?: number | null;
  weight_percent: number;
  unit: string;
  direction: string;
  contributes_to_score: boolean;
  tracking_only_note?: string | null;
  sample_size: number;
  source_link: string;
  scoring_basis_status: string;
  scoring_basis_note?: string | null;
}

export interface SessionFilterContext {
  function?: string | null;
  team?: string | null;
  position?: string | null;
  branch?: string | null;
  region?: string | null;
  performance_level?: string | null;
  month?: string | null;
  year?: number | null;
  employee_id?: string | null;
  last_confirmed_query?: ConfirmedQueryContext | null;
}

export interface AiChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface AiBarItem {
  label: string;
  value: number;
  display_value: string;
  target_value?: number | null;
  secondary_label?: string | null;
  severity: 'critical' | 'warning' | 'good' | 'neutral';
  color?: string | null;
}

export interface AiEntityListItem {
  id: string;
  title: string;
  subtitle: string;
  badge_text?: string | null;
  severity: 'critical' | 'warning' | 'good' | 'info';
  metric_value?: string | null;
  route_link?: string | null;
}

export interface AiKpiTableRow {
  kpi_key: string;
  kpi_label: string;
  weight_percent: number;
  actual_display: string;
  target_display: string;
  achievement_percent?: number | null;
  direction: string;
  people_below_target: number;
  status: 'critical' | 'warning' | 'good' | 'neutral' | 'info';
  unit?: string | null;
  contributes_to_score?: boolean;
  tracking_only_badge?: string | null;
}

export interface AiDecisionItem {
  id: string;
  priority: 'immediate' | 'high' | 'coaching' | 'strategic';
  priority_label: string;
  title: string;
  rationale: string;
  expected_impact: string;
  target_label: string;
  route_link?: string | null;
  cta_label?: string | null;
}

export interface AiTrendPoint {
  month: string;
  year: number;
  period_label: string;
  score: number;
  target: number;
  grade?: string | null;
}

export interface AiSpotlightMetricTile {
  label: string;
  value: string;
  sublabel?: string | null;
  tone: 'neutral' | 'good' | 'warning' | 'critical';
}

export interface AiSpotlightMetadata {
  kicker: string;
  entity_name: string;
  entity_id?: string | null;
  team: string;
  rank_label?: string | null;
  score: number;
  grade: 'A' | 'B' | 'C' | 'D' | 'E';
  change_vs_prev?: number | null;
  previous_month_label: string;
  six_month_delta?: number | null;
  target: number;
  headline_note?: string | null;
  tiles: AiSpotlightMetricTile[];
  kpi_chips: AiKpiTableRow[];
  trend_points: AiTrendPoint[];
}

export interface StructuredVisualCard {
  card_type:
    | 'horizontal_bar'
    | 'entity_list'
    | 'kpi_table'
    | 'guardrail_notice'
    | 'decision_playbook'
    | 'trend_spotlight';
  title: string;
  subtitle?: string | null;
  bars: AiBarItem[];
  items: AiEntityListItem[];
  kpi_rows: AiKpiTableRow[];
  decisions?: AiDecisionItem[];
  spotlight?: AiSpotlightMetadata | null;
  notice_text?: string | null;
}

export interface SourceCitationPill {
  label: string;
  category: 'period' | 'scope' | 'branch' | 'metric' | 'basis' | 'policy';
  warning?: boolean;
}

export interface DeepLinkCta {
  label: string;
  route: string;
  icon_key: 'insights' | 'team' | 'employee' | 'planning' | 'actions' | 'bsc';
}

export interface AiToolCallRecord {
  tool_name: string;
  arguments: Record<string, unknown>;
  records_evaluated: number;
}

export interface AiTurnTimingBreakdown {
  resolution_ms: number;
  provider_ms: number;
  database_ms: number;
  render_ms: number;
  trace_ms: number;
  total_ms: number;
}

export interface AiProviderUsageMetrics {
  router_mode: 'legacy' | 'shadow' | 'hybrid';
  route_used: string;
  provider_calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
  fallback_outcome: string;
  shadow_plan?: Record<string, unknown> | null;
}

export interface AiChatResponsePayload {
  trace_id: string;
  conversation_id?: string | null;
  turn_id?: string | null;
  context_version?: number;
  outcome?: TurnOutcomeType;
  answer_detail?: 'brief' | 'details';
  headline: string;
  narrative_bullets: string[];
  visual_cards: StructuredVisualCard[];
  citations: SourceCitationPill[];
  deep_links: DeepLinkCta[];
  primary_source_link?: DeepLinkCta | null;
  suggested_followups: string[];
  resolved_session_state: SessionFilterContext;
  scope_banner?: string | null;
  inherited_filters?: string[];
  clarification?: AiClarificationPrompt | null;
  structured_query?: StructuredQueryPlan | null;
  typed_evidence?: TypedMetricEvidence[];
  domain_guardrail_notes: string[];
  tool_calls: AiToolCallRecord[];
  provider_used: string;
  model_used: string;
  latency_ms: number;
  timings?: AiTurnTimingBreakdown;
  provider_usage?: AiProviderUsageMetrics;
  basis_warning?: string | null;
  cache_hit?: boolean;
}

export interface AiWatchingAlertItem {
  id: string;
  title: string;
  subtitle: string;
  severity: 'critical' | 'warning' | 'info';
  badge_text?: string | null;
  prompt_to_ask: string;
  deep_link?: string | null;
}

export interface AiGuardrailItem {
  label: string;
  description: string;
  verified: boolean;
}

export interface AiStarterPrompt {
  id: string;
  label: string;
  subtitle?: string | null;
  badge?: string | null;
  prompt: string;
  category: 'team' | 'kpi' | 'people' | 'branch' | 'governance';
  icon_key: 'alert' | 'users' | 'chart' | 'shield';
}

export interface AiEligibleTeamItem {
  value: string;
  label: string;
  function: string;
  badge?: string | null;
}

export interface AiWatchingPayload {
  resolved_session_state: SessionFilterContext;
  alerts: AiWatchingAlertItem[];
  guardrails: AiGuardrailItem[];
  starter_prompts: AiStarterPrompt[];
  eligible_teams?: AiEligibleTeamItem[];
  eligible_functions?: string[];
  eligible_branches?: string[];
  eligible_levels?: string[];
  summary_score?: number | null;
  summary_score_change?: number | null;
  measured_records: number;
}
