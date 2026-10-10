/**
 * Executive + Function Summary v1 data contract.
 *
 * Mirrors `GET /api/executive/summary` as specified in
 * /workspace/pms-exec-function-summary-build/API_NEEDS.md (plus CoS decisions:
 * `weighted_gap_points` on drivers, an optional 95/90/80/70 `grade_counts_v2`).
 * Until the endpoint exists the page composes the same shape from existing
 * endpoints (`compose.ts`). Every field the composition cannot honestly
 * produce is `null` / empty, and `meta.unavailable` lists those sections so
 * widgets hide or soften instead of showing invented numbers.
 */
import type { GradeClass } from '../../constants/grades';
import type { BasisComparisonContext } from '../evaluation/scoringBasisComparison';
import type { InsightPeriod, InsightTrendStatus, InsightTargetStatus } from '../insights/types';

export type ExecutiveView = 'corporate' | 'managerial' | 'function';
export type ExecutiveFunction = 'Call Center' | 'RCM' | 'Pre-Approvals' | 'Marketing' | 'Sales' | 'CSR' | 'Pharmacy';

export type ExecutivePeriod = InsightPeriod;

export interface ExecutivePeriodBlock {
  requested: ExecutivePeriod | null;
  effective: ExecutivePeriod | null;
  previous: ExecutivePeriod | null;
  fallback_applied: boolean;
  notice: string | null;
}

export interface ExecutiveDataStatus {
  has_data: boolean;
  last_upload: { period: ExecutivePeriod; employees: number; uploaded_at: string | null; uploaded_by: string | null } | null;
  effective_uploaded_at?: string | null;
}

export interface ExecutiveScope {
  view: ExecutiveView;
  role: string;
  locked: { region: boolean; function: boolean; team: boolean };
  team: string | null;
  function: string | null;
  region: string | null;
  accessible_functions: string[];
  branch?: string | null;
  performance_level?: string | null;
  position?: string | null;
}

export interface ExecutiveTrendPoint {
  period: ExecutivePeriod;
  score: number | null;
  comparison_score: number | null;
  target: number;
  measured_records?: number;
  basis_context?: BasisComparisonContext | null;
}

export interface ExecutiveHero {
  label: string;
  score: number | null;
  previous_score: number | null;
  change: number | null;
  gap: number | null;
  target: number;
  grade: GradeClass | null;
  employees: number;
  teams_count: number;
  functions_count: number;
  story: {
    headline: string | null;
    biggest_drag: { function: string | null; team: string | null; kpi_key: string | null; kpi_label: string | null } | null;
    most_improved: { function: string; change: number } | null;
  } | null;
  comparison: { label: string; score: number | null; difference: number | null } | null;
}

export interface ExecutiveFunctionCard {
  function: ExecutiveFunction;
  score: number | null;
  previous_score: number | null;
  change: number | null;
  gap: number | null;
  grade: GradeClass | null;
  employees: number;
  teams: string[];
  regions: string[];
  /** Consecutive month-over-month falls ending at the effective period; null = unknown. */
  falling_months: number | null;
  trend: Array<{ period: ExecutivePeriod; score: number | null }>;
  is_most_improved: boolean;
  basis_context?: BasisComparisonContext | null;
}

export interface ExecutiveRegion {
  region: string;
  label: string;
  score: number | null;
  previous_score: number | null;
  change: number | null;
  gap: number | null;
  grade: GradeClass | null;
  employees: number;
  teams_count: number;
  teams: string[];
  gap_share_percent: number | null;
  headcount_share_percent: number | null;
}

export interface ExecutiveDriver {
  kpi_key: string | null;
  kpi_label: string;
  team: string | null;
  function: string | null;
  kpi_direction: string | null;
  unit: string | null;
  current_value: number | null;
  previous_value: number | null;
  raw_change: number | null;
  change_value: number | null;
  trend_status: InsightTrendStatus | null;
  gap_value: number | null;
  achievement_percent: number | null;
  weight: number | null;
  /** Month-over-month weighted-contribution change (existing insights meaning; CoS: unchanged). */
  impact_points: number | null;
  /** weight × gap in score points (Backend adding; preferred for ranking negatives). */
  weighted_gap_points?: number | null;
  /** Gap closed vs last month (positive = improvement). */
  impact_change_points?: number | null;
  insight_id?: string | null;
}

export type ExecutiveTeamFlag =
  | 'grade_c'
  | 'grade_d'
  | 'grade_e'
  | 'falling_2_months'
  | 'lowest_in_function'
  | 'kpi_worsening_2_months'
  | 'below_function_avg';

export interface ExecutiveTeam {
  team: string;
  /** Marketing role groups retain their source team and never become synthetic teams. */
  position?: string | null;
  source_team?: string;
  function: string | null;
  regions: string[];
  employees: number;
  score: number | null;
  previous_score: number | null;
  change: number | null;
  gap: number | null;
  grade: GradeClass | null;
  trend: Array<{ period: ExecutivePeriod; score: number | null }>;
  vs_function_avg: number | null;
  rank_in_function: number | null;
  flags: ExecutiveTeamFlag[];
  flag_detail: {
    kpi_key: string | null;
    kpi_label: string;
    kpi_direction: string | null;
    current_value: number | null;
    target_value: number | null;
    unit: string | null;
    text: string;
  } | null;
  basis_context?: BasisComparisonContext | null;
}

export interface ExecutiveGradeDistribution {
  total: number;
  counts: Record<GradeClass, number>;
  percents: Record<GradeClass, number>;
  previous_counts: Record<GradeClass, number> | null;
  movement: Record<GradeClass, number> | null;
}

export interface ExecutiveKpiRow {
  kpi_key: string;
  kpi_label: string;
  kpi_direction: string | null;
  unit: string | null;
  actual: number | null;
  target: number | null;
  previous_actual: number | null;
  gap_value: number | null;
  raw_gap: number | null;
  raw_change: number | null;
  change_value: number | null;
  trend_status: InsightTrendStatus | null;
  weight: number | null;
  achievement_percent: number | null;
  grade: GradeClass | null;
  target_status: InsightTargetStatus | null;
  teams: string[];
}

export interface ExecutiveLevel {
  level: string;
  employees: number;
  score: number | null;
  previous_score: number | null;
  change: number | null;
  grade: GradeClass | null;
}

export interface ExecutivePerson {
  employee_id: string;
  name: string;
  position: string | null;
  team?: string;
  region?: string | null;
  performance_level?: string;
  score: number | null;
  previous_score: number | null;
  change: number | null;
  grade: GradeClass | null;
}

export interface ExecutivePeople {
  bottom: ExecutivePerson[];
  biggest_drops: ExecutivePerson[];
  top: ExecutivePerson[];
  below_90?: ExecutivePerson[];
}

export interface ExecutiveActionItem {
  id: string;
  title: string;
  team: string | null;
  region: string | null;
  employee_name: string | null;
  owner: { id: string; name: string } | null;
  due_date: string | null;
  status: string;
  follow_up_state: string | null;
  employee_id?: string | null;
  month?: string;
}

export interface ExecutiveCorrectiveActions {
  /** Full period-scoped evidence for read-only dashboard analysis, not the four open follow-up rows. */
  analytics?: ExecutiveActionAnalytics;
  summary: {
    as_of: string;
    open: number;
    in_progress?: number;
    overdue: number;
    due_this_week: number;
    closed_in_month: number | null;
  };
  actions: ExecutiveActionItem[];
}

export interface ExecutiveActionAnalytics {
  actions: Array<{
    id: string;
    team: string | null;
    employee_id: string | null;
    action_type: string;
    kpi_mentions: string[];
  }>;
  unassigned_period: number;
}

export interface ExecutiveHighlights {
  most_improved: { type: 'function' | 'team'; name: string; change: number } | null;
  lowest_in_function: { team: string; function: string; score: number } | null;
}

/** Sections the page may render; listed in `meta.unavailable` when their data does not exist yet. */
export type ExecutiveSection =
  | 'upload_meta'
  | 'function_trend'
  | 'function_average'
  | 'company_average'
  | 'drivers'
  | 'drivers_weighted_gap'
  | 'grade_mix'
  | 'corrective_actions'
  | 'kpis'
  | 'people'
  | 'team_trend';

export interface ExecutiveSummary {
  period: ExecutivePeriodBlock;
  data_status: ExecutiveDataStatus;
  scope: ExecutiveScope;
  hero: ExecutiveHero;
  trend: ExecutiveTrendPoint[];
  functions: ExecutiveFunctionCard[];
  regions: ExecutiveRegion[];
  drivers: { negative: ExecutiveDriver[]; positive: ExecutiveDriver[] };
  teams: ExecutiveTeam[];
  grade_distribution: ExecutiveGradeDistribution | null;
  kpis: ExecutiveKpiRow[];
  levels: ExecutiveLevel[];
  people: ExecutivePeople | null;
  highlights: ExecutiveHighlights;
  corrective_actions: ExecutiveCorrectiveActions | null;
  /** Available periods (newest first) for the Date filter. */
  periods: ExecutivePeriod[];
  meta: {
    source: 'api' | 'composed';
    unavailable: ExecutiveSection[];
    /** Neutral label for the driver impact metric actually used. */
    driver_metric: 'weighted_gap' | 'contribution_change';
  };
}
