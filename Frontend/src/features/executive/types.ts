/**
 * Executive + Function Summary v1 data contract.
 *
 * The shape the Executive and Function Summary pages render. The backend has no
 * summary route for it (see API_NEEDS.md; CoS decisions: `weighted_gap_points`
 * on drivers, an optional 95/90/80/70 `grade_counts_v2`), so the page composes it
 * from existing endpoints (`compose.ts`). Every field the composition cannot honestly
 * produce is `null` / empty, and `meta.unavailable` lists those sections so
 * widgets hide or soften instead of showing invented numbers.
 */
import type { GradeClass } from '../../constants/grades';
import type { BasisComparisonContext } from '../evaluation/scoringBasisComparison';
import type { InsightPeriod, InsightTrendStatus, InsightTargetStatus } from '../insights/types';

export type ExecutiveView = 'corporate' | 'managerial' | 'function';
export type ExecutiveFunction = 'Call Center' | 'RCM' | 'Pre-Approvals' | 'Marketing' | 'Sales' | 'CSR' | 'Pharmacy' | 'Finance' | 'Human Resources' | 'IT' | 'Administration';

export type ExecutivePeriod = InsightPeriod;

export interface ExecutivePeriodBlock {
  requested: ExecutivePeriod | null;
  effective: ExecutivePeriod | null;
  previous: ExecutivePeriod | null;
  fallback_applied: boolean;
  notice: string | null;
  /** Set when the page shows a range of months; `effective` is then the range's last month. */
  range?: ExecutiveRangeBlock | null;
}

/** A range of months, averaged person-first. Comparison is the previous range of the same length. */
export interface ExecutiveRangeBlock {
  start: ExecutivePeriod;
  end: ExecutivePeriod;
  /** Every month in the range, oldest first; months without counted data are included. */
  months: ExecutivePeriod[];
  months_with_data: number;
  /** The range of the same length immediately before; null when it has no counted data in scope. */
  previous: { start: ExecutivePeriod; end: ExecutivePeriod; months_with_data: number } | null;
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
  /** True for the months inside the selected range (range mode); the trend itself stays monthly. */
  in_range?: boolean;
}

export type ExecutiveScoreBasis = 'people_average' | 'leader_scorecard' | 'team_scorecard';

export interface ExecutiveHero {
  label: string;
  score: number | null;
  previous_score: number | null;
  change: number | null;
  gap: number | null;
  target: number;
  grade: GradeClass | null;
  /** What the headline number is. Corporate and function views are a people average. */
  score_basis?: ExecutiveScoreBasis;
  employees: number;
  teams_count: number;
  functions_count: number;
  story: {
    headline: string | null;
    biggest_drag: {
      function: string | null;
      team: string | null;
      kpi_key: string | null;
      kpi_label: string | null;
      /** This function's share of the scope gap. The KPI belongs to this function. */
      share_percent?: number | null;
      score?: number | null;
      /** Lowest team's own KPI text, used only when no driver in this function was returned. */
      cause?: string | null;
    } | null;
    most_improved: { function: string; change: number } | null;
  } | null;
  comparison: { label: string; score: number | null; difference: number | null } | null;
}

/** People average for one side of a function that measures both groups. */
export interface ExecutiveFunctionCohort {
  employees: number;
  score: number | null;
  gap: number | null;
  grade: GradeClass | null;
  change: number | null;
  teams: string[];
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
  /**
   * Call Center and RCM only, and only when both sides have people.
   * Employees are the operational teams. Supportive positions are the team
   * named the same as the function. The function score stays the people average of both.
   */
  cohorts?: { employees: ExecutiveFunctionCohort; support: ExecutiveFunctionCohort } | null;
  /** Consecutive month-over-month falls ending at the effective period; null = unknown. */
  falling_months: number | null;
  trend: Array<{ period: ExecutivePeriod; score: number | null }>;
  is_most_improved: boolean;
  /** Share of this scope's gap: max(100 − score, 0) × people. */
  gap_share_percent?: number | null;
  /** The function number is the average of its people, including where a team row uses a leader scorecard. */
  score_basis?: ExecutiveScoreBasis;
  lowest_team?: {
    team: string;
    score: number;
    kpi: string | null;
    score_basis?: ExecutiveScoreBasis;
  } | null;
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
  /** Share of this scope's gap: max(100 − score, 0) × people. */
  gap_share_percent?: number | null;
  score_basis?: ExecutiveScoreBasis;
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
  /** Combined shares computed from counts (A+B, D+E), rounded once. Optional for hand-built fixtures. */
  combined_percents?: { AB: number; DE: number };
  /** Distinct people in the graded scope (the shares above count employee-month rows). */
  people?: number;
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
  /** Range mode: the target differs between people or months, so `target` is null and the UI shows "Varies". */
  target_varies?: boolean;
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
  /** Range mode: counted months behind the person's score (the average over them). */
  months?: number;
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
  /** Action type badge (Coaching, PIP, ...). */
  action_type?: string | null;
  /** The action text the manager wrote; the card shows its first line and the full text on expand. */
  action_text?: string | null;
  /** Reason for the action (root cause note). */
  root_cause?: string | null;
  linked_kpi_key?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
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
  /** Four-row preview (kept for other consumers). */
  actions: ExecutiveActionItem[];
  /** Full list for the Corrective actions card: open plus closed this period, overdue first. */
  rows?: ExecutiveActionItem[];
}

export interface ExecutiveActionAnalytics {
  actions: Array<{
    id: string;
    team: string | null;
    employee_id: string | null;
    action_type: string;
    kpi_mentions: string[];
    root_cause_note?: string | null;
  }>;
  unassigned_period: number;
  /** Actions queued on this device and not yet synced, in the active period. Shown as Pending Sync only. */
  pending_sync?: Array<{ id: string; team: string | null }>;
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
  /** Evaluation-basis note for the selected month on this scope (null when the scope has none). */
  basis_context?: BasisComparisonContext | null;
  /** Available periods (newest first) for the Date filter. */
  periods: ExecutivePeriod[];
  meta: {
    source: 'api' | 'composed';
    unavailable: ExecutiveSection[];
    /** Neutral label for the driver impact metric actually used. */
    driver_metric: 'weighted_gap' | 'contribution_change';
  };
}
