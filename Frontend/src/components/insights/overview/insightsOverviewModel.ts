/**
 * Pure data mapping for the Insights redesign B overview (Figma 18:3).
 *
 * Every value rendered by the overview sections is derived here from the
 * existing `GET /api/insights/workspace` payload. Nothing in this module
 * invents numbers: when the API has no value the helpers return `null` and the
 * UI renders an explicit empty / "N/A" state instead.
 */
import { GRADE_THRESHOLDS } from '../../../constants/grades';
import type {
  InsightDriver,
  InsightExecutiveStory,
  InsightKpiTrend,
  InsightOverallTrendPoint,
  InsightPeopleContributionAnalysis,
  InsightPersonContribution,
  InsightScopeSummary,
  InsightsWorkspace,
} from '../../../features/insights/types';

export type TeamSummary = InsightsWorkspace['team_summaries'][number];

export function cleanScope(value: string) {
  return value.replace(/Â/g, '');
}

export function formatPercent(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'N/A';
  return `${value.toFixed(digits)}%`;
}

export function formatSignedPercent(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'N/A';
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}%`;
}

/** Same unit handling as the rest of Insights: `%` KPIs may be stored as 0–1 ratios. */
export function formatMetric(value: number | null, unit: string | null) {
  if (value === null) return 'N/A';
  if (unit === '%') return `${(Math.abs(value) <= 1 ? value * 100 : value).toFixed(1)}%`;
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${unit ? ` ${unit}` : ''}`;
}

/**
 * Actual as a percentage of target, honouring the KPI scoring direction.
 * Mirrors Backend `_target_achievement` but is left uncapped so a trend can
 * show over-achievement. Returns `null` when it cannot be measured.
 */
export function achievementPercent(
  actual: number | null | undefined,
  target: number | null | undefined,
  direction: string | null | undefined,
): number | null {
  if (actual === null || actual === undefined || target === null || target === undefined) return null;
  if (!Number.isFinite(actual) || !Number.isFinite(target) || target <= 0) return null;
  if (direction === 'lower_better') return actual <= 0 ? 100 : (target / actual) * 100;
  if (direction === 'higher_better') return (actual / target) * 100;
  return null;
}

/**
 * Achievement % for display: prefers the API's PR #15 `achievement_percent`
 * (direction-aware, capped 0–100) and only recomputes it for older APIs.
 */
export function resolveAchievement(
  apiPercent: number | null | undefined,
  actual: number | null | undefined,
  target: number | null | undefined,
  direction: string | null | undefined,
): number | null {
  if (apiPercent !== null && apiPercent !== undefined && Number.isFinite(apiPercent)) return apiPercent;
  return achievementPercent(actual, target, direction);
}

export type KpiStatus = 'on_track' | 'at_risk' | 'critical';

/** Per-point KPI status: the API's PR #15 `status`, else the same 100% / 70% thresholds. */
export function resolveKpiStatus(apiStatus: string | null | undefined, achievement: number | null): KpiStatus | null {
  if (apiStatus === 'on_track' || apiStatus === 'at_risk' || apiStatus === 'critical') return apiStatus;
  if (achievement === null) return null;
  if (achievement >= 100) return 'on_track';
  if (achievement >= 70) return 'at_risk';
  return 'critical';
}

export type MovementTone = 'good' | 'bad' | 'flat' | 'unknown';

/**
 * Good / bad meaning of a movement. Prefers the API's PR #15 `trend_status`,
 * then its direction-adjusted `change_value` (+ = improvement), and only then
 * recomputes from the raw delta and the KPI direction.
 */
export function resolveMovementTone({
  trendStatus, changeValue, rawDelta, direction,
}: {
  trendStatus?: string | null;
  changeValue?: number | null;
  rawDelta?: number | null;
  direction?: string | null;
}): MovementTone {
  if (trendStatus === 'improving') return 'good';
  if (trendStatus === 'declining') return 'bad';
  if (trendStatus === 'stable') return 'flat';
  if (changeValue !== null && changeValue !== undefined && Number.isFinite(changeValue)) {
    // changeValue is already normalized so positive always means improvement.
    if (Math.abs(changeValue) < 1e-9) return 'flat';
    return changeValue > 0 ? 'good' : 'bad';
  }
  return movementTone(rawDelta, direction);
}

/**
 * Whether a change in a KPI's raw value is an improvement, using the KPI
 * `direction` the API already returns (`higher_better` / `lower_better`).
 * For lower-is-better KPIs (e.g. Rejection Rate, CPL) an increase is bad.
 * Unknown directions stay neutral instead of being guessed.
 */
export function movementTone(delta: number | null | undefined, direction: string | null | undefined): MovementTone {
  if (delta === null || delta === undefined || !Number.isFinite(delta)) return 'unknown';
  if (Math.abs(delta) < 1e-9) return 'flat';
  if (direction === 'lower_better') return delta < 0 ? 'good' : 'bad';
  if (direction === 'higher_better') return delta > 0 ? 'good' : 'bad';
  return 'unknown';
}

export interface TrendPoint {
  label: string;
  key: string;
  /** Plotted value in % (overall score, or KPI achievement as % of target). Higher is always better. */
  actual: number | null;
  /** Target in the same % scale. */
  target: number | null;
  /** Raw KPI values for the leading-KPI fallback (direction-aware movement in the tooltip). */
  raw?: {
    actual: number | null;
    target: number | null;
    previous: number | null;
    unit: string | null;
    direction: string | null;
    /** PR #15 per-point fields, when the API sends them. */
    trendStatus?: string | null;
    changeValue?: number | null;
    status?: string | null;
  };
}

export interface TrendSeries {
  source: 'overall' | 'kpi';
  points: TrendPoint[];
  kpiLabel: string | null;
  direction: string | null;
  unit: string | null;
}

/**
 * Six-month "Performance trend" series for the leading-KPI fallback. The
 * workspace only exposes a six-month series for the leading KPI
 * (`kpi_trend`), so actual and target are normalised to "% of target"
 * (target line = 100%), honouring the KPI direction.
 */
export function buildPerformanceTrend(trend: InsightKpiTrend | null | undefined): TrendPoint[] {
  if (!trend) return [];
  return trend.points.map((point, index) => ({
    label: point.period.month.slice(0, 3),
    key: point.period.key,
    actual: resolveAchievement(point.achievement_percent, point.actual_value, point.target_value, trend.direction),
    target: point.target_value !== null && point.target_value > 0 ? 100 : null,
    raw: {
      actual: point.actual_value,
      target: point.target_value,
      previous: index > 0 ? trend.points[index - 1].actual_value : null,
      unit: trend.unit,
      direction: trend.direction,
      trendStatus: point.trend_status ?? null,
      changeValue: point.change_value ?? null,
      status: point.status ?? null,
    },
  }));
}

/** Overall score series (`overall_trend`, proposed backend field), same scale as the summary's Current score. */
export function buildOverallTrend(points: InsightOverallTrendPoint[] | null | undefined): TrendPoint[] {
  if (!points?.length) return [];
  return points.map((point) => ({
    label: point.period.month.slice(0, 3),
    key: point.period.key,
    actual: point.score,
    target: point.target,
  }));
}

/**
 * Prefer the overall score series. Once the API sends `overall_trend` (even an
 * empty one) it is the only source, so the latest month always matches the
 * Current score and an empty scope shows an empty state, never a KPI. Only an
 * older API without the field falls back to the leading KPI, clearly labelled.
 */
export function selectTrendSeries(
  overall: InsightOverallTrendPoint[] | null | undefined,
  kpiTrend: InsightKpiTrend | null | undefined,
): TrendSeries {
  if (Array.isArray(overall)) {
    return { source: 'overall', points: buildOverallTrend(overall), kpiLabel: null, direction: 'higher_better', unit: '%' };
  }
  return {
    source: 'kpi',
    points: buildPerformanceTrend(kpiTrend),
    kpiLabel: kpiTrend?.kpi_label ?? null,
    direction: kpiTrend?.direction ?? null,
    unit: kpiTrend?.unit ?? null,
  };
}

export interface DriverSplit {
  negative: InsightDriver[];
  positive: InsightDriver[];
  maxMagnitude: number;
}

export function splitDrivers(drivers: InsightDriver[], limit = 3): DriverSplit {
  const negative = drivers
    .filter((driver) => driver.impact_points < 0)
    .sort((a, b) => a.impact_points - b.impact_points)
    .slice(0, limit);
  const positive = drivers
    .filter((driver) => driver.impact_points > 0)
    .sort((a, b) => b.impact_points - a.impact_points)
    .slice(0, limit);
  const maxMagnitude = Math.max(0, ...[...negative, ...positive].map((driver) => Math.abs(driver.impact_points)));
  return { negative, positive, maxMagnitude };
}

/** Bar width as a share of the largest visible driver (0–100). */
export function barShare(value: number, max: number) {
  if (!max || !Number.isFinite(value)) return 0;
  return Math.min(100, (Math.abs(value) / max) * 100);
}

export function teamGap(team: TeamSummary): number | null {
  if (team.gap_points !== undefined && team.gap_points !== null) return team.gap_points;
  return team.current_score === null ? null : Number((team.current_score - 100).toFixed(1));
}

export function geographyGap(summary: InsightScopeSummary): number | null {
  if (summary.gap_points !== null) return summary.gap_points;
  return summary.current_score === null ? null : Number((summary.current_score - 100).toFixed(1));
}

/** Teams ordered by the API (gap contribution first), limited for the overview card. */
export function teamsNeedingAttention(teams: TeamSummary[], limit = 5) {
  return teams.filter((team) => team.current_score !== null).slice(0, limit);
}

/** Teams graded D or E (score below the C threshold), lowest score first. */
export function lowPerformingTeams(teams: TeamSummary[]) {
  return teams
    .filter((team) => team.current_score !== null && team.current_score < GRADE_THRESHOLDS.C)
    .sort((a, b) => (a.current_score ?? 0) - (b.current_score ?? 0));
}

export interface PersonToReview extends InsightPersonContribution {
  achievement: number | null;
}

/** Negative contributors for the leading KPI, largest weighted impact first. */
export function peopleToReview(
  analysis: InsightPeopleContributionAnalysis | null | undefined,
  limit = 3,
): PersonToReview[] {
  if (!analysis) return [];
  return analysis.rows
    .filter((row) => row.classification === 'negative')
    .sort((a, b) => (a.weighted_impact ?? 0) - (b.weighted_impact ?? 0))
    .slice(0, limit)
    .map((row) => ({
      ...row,
      achievement: resolveAchievement(row.achievement_percent, row.current_value, row.target_value, row.direction ?? analysis.direction),
    }));
}

/** Sparkline points for the 72×26 Figma sparkline box (x 4→68, y 6→18). */
export function sparklinePoints(values: Array<number | null>): Array<{ x: number; y: number }> {
  const measured = values.filter((value): value is number => value !== null && Number.isFinite(value));
  if (measured.length < 2) return [];
  const min = Math.min(...measured);
  const max = Math.max(...measured);
  const step = 64 / (measured.length - 1);
  return measured.map((value, index) => ({
    x: 4 + index * step,
    y: max === min ? 12 : 18 - ((value - min) / (max - min)) * 12,
  }));
}

export type MoreAnalysisKey = 'kpi' | 'role' | 'weighted' | 'alerts';

export const MORE_ANALYSIS_KEYS: MoreAnalysisKey[] = ['kpi', 'role', 'weighted', 'alerts'];

/** "Review <KPI> first — largest weighted gap." (Figma 29:2), from the executive story's primary driver. */
export function priorityFocusText(story: InsightExecutiveStory | null | undefined) {
  if (!story) return 'Review data coverage before making a performance decision.';
  if (story.primary_driver) return `Review ${cleanScope(story.primary_driver)} first — largest weighted gap.`;
  return cleanScope(story.recommended_focus);
}
