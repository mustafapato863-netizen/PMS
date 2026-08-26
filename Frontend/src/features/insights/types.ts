export type InsightSeverity = 'critical' | 'risk' | 'opportunity' | 'information';
export type InsightType = 'performance' | 'kpi_driver' | 'employee_risk' | 'opportunity' | 'data_quality';

export interface InsightPeriod {
  year: number;
  month: string;
  key: string;
}

export interface InsightEvidence {
  label: string;
  value: string;
}

export interface InsightDetail {
  current_value: number | null;
  previous_value: number | null;
  target_value: number | null;
  unit: string | null;
  direction: string | null;
  impact_points: number | null;
  affected_teams: string[];
  affected_positions: string[];
  affected_employees: string[];
  evidence: InsightEvidence[];
  warnings: string[];
  recommended_focus: string;
}

export interface InsightItem {
  id: string;
  severity: InsightSeverity;
  insight_type: InsightType;
  title: string;
  explanation: string;
  scope: string;
  impact_points: number | null;
  trend_label: string;
  priority_reason: string;
  status: string;
  team: string | null;
  performance_level: string | null;
  position: string | null;
  employee_id: string | null;
  kpi_key: string | null;
  detail: InsightDetail;
  planning_context: Record<string, string | number | null>;
}

export interface InsightDriver {
  id: string;
  driver: string;
  scope: string;
  impact_points: number;
  direction: 'positive' | 'negative';
  insight_id: string;
  trend?: Array<{ period: InsightPeriod; impact_points: number | null }>;
}

export interface InsightRisk {
  key: string;
  label: string;
  count: number;
  explanation: string;
  filter_type: string;
}

export interface InsightScopeSummary {
  scope: string;
  current_score: number | null;
  previous_score: number | null;
  score_change: number | null;
  gap_points: number | null;
  gap_contribution_percent: number | null;
  impacted_employees: number;
  total_employees: number;
  affected_percentage: number | null;
}

export interface InsightExecutiveStory {
  headline: string;
  scope_label: string;
  current_score: number | null;
  target_score: number;
  gap_points: number | null;
  score_change: number | null;
  primary_scope: string | null;
  primary_scope_contribution_percent: number | null;
  primary_driver: string | null;
  primary_driver_impact: number | null;
  recommended_focus: string;
  confidence: 'high' | 'partial' | 'low';
  evidence: InsightEvidence[];
}

export type PersonContributionClassification = 'negative' | 'positive' | 'affected' | 'data_issue';

export interface InsightPersonContribution {
  employee_id: string;
  employee_name: string;
  team: string;
  performance_level: string;
  position: string;
  kpi_key: string;
  kpi_label: string;
  unit: string | null;
  direction: string | null;
  current_value: number | null;
  target_value: number | null;
  gap: number | null;
  weighted_impact: number | null;
  trend: number | null;
  severity: string;
  classification: PersonContributionClassification;
}

export interface InsightPeopleContributionAnalysis {
  kpi_key: string;
  kpi_label: string;
  unit: string | null;
  direction: string | null;
  total_employees: number;
  negative_contributors: number;
  positive_contributors: number;
  data_issues: number;
  rows: InsightPersonContribution[];
}

export interface InsightKpiTrendPoint {
  period: InsightPeriod;
  actual_value: number | null;
  target_value: number | null;
  measured_records: number;
}

export interface InsightKpiTrend {
  kpi_key: string;
  kpi_label: string;
  unit: string | null;
  direction: string | null;
  points: InsightKpiTrendPoint[];
}

export interface InsightRoleSummary {
  role: string;
  team: string;
  current_score: number | null;
  previous_score: number | null;
  movement: number | null;
  net_impact: number | null;
  affected_employees: number;
  total_employees: number;
  primary_insight_id: string | null;
}

export interface InsightKpiOverviewPoint {
  period: InsightPeriod;
  total_kpis: number;
  on_track: number;
  at_risk: number;
  critical: number;
}

export interface InsightKpiOverview {
  total_kpis: number;
  on_track: number;
  at_risk: number;
  critical: number;
  points: InsightKpiOverviewPoint[];
}

export interface InsightOptions {
  periods: InsightPeriod[];
  regions: string[];
  teams: string[];
  performance_levels: string[];
  positions: string[];
  employees: Array<{ id: string; name: string; team: string; position: string; performance_level: string }>;
  kpis: Array<{ key: string; label: string }>;
  severities: InsightSeverity[];
  insight_types: InsightType[];
  statuses: string[];
}

export interface InsightsWorkspace {
  summary: {
    critical: number;
    at_risk: number;
    opportunities: number;
    data_issues: number;
    critical_issues: number;
    negative_weighted_drivers: number;
    positive_weighted_drivers: number;
    weighted_negative_impact: number;
    weighted_positive_impact: number;
    weighted_net_impact: number;
    analyzed_kpis: number;
    expected_kpis: number;
    coverage_percent: number | null;
  };
  priority_insights: InsightItem[];
  team_analyses: InsightItem[];
  performance_drivers: InsightDriver[];
  risks: InsightRisk[];
  opportunities: InsightItem[];
  data_issues: InsightItem[];
  people_contribution_analysis: InsightPeopleContributionAnalysis | null;
  kpi_trend: InsightKpiTrend | null;
  role_summaries?: InsightRoleSummary[];
  kpi_overview?: InsightKpiOverview;
  team_summaries: Array<{
    team: string;
    current_score: number | null;
    previous_score: number | null;
    score_change: number | null;
    gap_points?: number | null;
    gap_contribution_percent?: number | null;
    impacted_employees: number;
    total_employees: number;
    affected_percentage?: number | null;
    critical: number;
    at_risk: number;
    opportunities: number;
    main_insight_id: string | null;
    main_cause: string | null;
  }>;
  geography_summaries?: InsightScopeSummary[];
  executive_story?: InsightExecutiveStory | null;
  options: InsightOptions;
  comparison: { current: InsightPeriod | null; previous: InsightPeriod | null; is_adjacent: boolean; note: string | null };
  deferred_capabilities: string[];
}

export interface InsightFilters {
  periodKey?: string;
  region?: string;
  team?: string;
  performanceLevel?: string;
  position?: string;
  employeeId?: string;
  kpi?: string;
  severity?: string;
  insightType?: string;
  status?: string;
}
