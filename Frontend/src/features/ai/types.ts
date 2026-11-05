export interface SessionFilterContext {
  function?: string | null;
  team?: string | null;
  branch?: string | null;
  region?: string | null;
  performance_level?: string | null;
  month?: string | null;
  year?: number | null;
  employee_id?: string | null;
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
  status: 'critical' | 'warning' | 'good' | 'neutral';
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

export interface AiChatResponsePayload {
  trace_id: string;
  headline: string;
  narrative_bullets: string[];
  visual_cards: StructuredVisualCard[];
  citations: SourceCitationPill[];
  deep_links: DeepLinkCta[];
  suggested_followups: string[];
  resolved_session_state: SessionFilterContext;
  domain_guardrail_notes: string[];
  tool_calls: AiToolCallRecord[];
  provider_used: string;
  model_used: string;
  latency_ms: number;
  basis_warning?: string | null;
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

export interface AiWatchingPayload {
  resolved_session_state: SessionFilterContext;
  alerts: AiWatchingAlertItem[];
  guardrails: AiGuardrailItem[];
  starter_prompts: AiStarterPrompt[];
  summary_score?: number | null;
  summary_score_change?: number | null;
  measured_records: number;
}
