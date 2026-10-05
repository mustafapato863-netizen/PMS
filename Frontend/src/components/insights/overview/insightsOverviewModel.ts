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
  InsightKpiTrend,
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

export interface TrendPoint {
  label: string;
  key: string;
  actual: number | null;
  target: number | null;
}

/**
 * Six-month "Performance trend" series. The workspace exposes a six-month
 * series only for the leading KPI (`kpi_trend`), so actual and target are
 * normalised to "% of target" (target line = 100%).
 */
export function buildPerformanceTrend(trend: InsightKpiTrend | null | undefined): TrendPoint[] {
  if (!trend) return [];
  return trend.points.map((point) => ({
    label: point.period.month.slice(0, 3),
    key: point.period.key,
    actual: achievementPercent(point.actual_value, point.target_value, trend.direction),
    target: point.target_value !== null && point.target_value > 0 ? 100 : null,
  }));
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
      achievement: achievementPercent(row.current_value, row.target_value, row.direction ?? analysis.direction),
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
