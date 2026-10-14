/**
 * Pure data mapping for the Insights overview sections.
 *
 * Every value rendered by the overview sections is derived here from the
 * existing `GET /api/insights/workspace` payload. Nothing in this module
 * invents numbers: when the API has no value the helpers return `null` and the
 * UI renders an explicit empty / "N/A" state instead.
 *
 * Only helpers with a live consumer stay here. Helpers that nothing imports
 * were removed with the overview sections that used them.
 */
import type {
  InsightPeopleContributionAnalysis,
  InsightPersonContribution,
} from '../../../features/insights/types';

/**
 * Actual as a percentage of target, honouring the KPI scoring direction.
 * Mirrors Backend `_target_achievement` but is left uncapped so a trend can
 * show over-achievement. Returns `null` when it cannot be measured.
 */
function achievementPercent(
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
function movementTone(delta: number | null | undefined, direction: string | null | undefined): MovementTone {
  if (delta === null || delta === undefined || !Number.isFinite(delta)) return 'unknown';
  if (Math.abs(delta) < 1e-9) return 'flat';
  if (direction === 'lower_better') return delta < 0 ? 'good' : 'bad';
  if (direction === 'higher_better') return delta > 0 ? 'good' : 'bad';
  return 'unknown';
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
