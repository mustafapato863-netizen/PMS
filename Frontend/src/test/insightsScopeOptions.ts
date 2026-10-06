/**
 * Test / review-harness mirror of the backend option scoping for
 * GET /api/insights/workspace. Not used by the app.
 *
 * - `pr14` mirrors PR #14 (`InsightsService._options` + `_resolve_current_period`):
 *   every list except `periods` is limited to the resolved current period
 *   (explicit month, else the latest period of the filtered scope), each list
 *   is narrowed by the *other* selections, and `functions` / `team_functions`
 *   come from `report_scope.functions_for_team`.
 * - `legacy` mirrors main @ 0d4d48d: regions unscoped, teams by region,
 *   levels by region + team, no `functions` / `team_functions`.
 */
import type { InsightFilters, InsightOptions, InsightPeriod } from '../features/insights/types';
import { apiTeamParam, teamBelongsToFunction } from '../features/insights/filterCascade';
import { isCallCenterTeam, isPreApprovalsUaeTeam, isRcmTeam } from '../types';

export interface ScopeRecord {
  region: string;
  team: string;
  level: string;
  period: string;
}

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

export function periodFromKey(key: string): InsightPeriod {
  const [year, month] = key.split('-').map(Number);
  return { year, month: MONTHS[month - 1], key };
}

/** Mirror of PR #14 `functions_for_team` (broadest first; standalone teams are their own function). */
export function functionsForTeam(team: string): string[] {
  const parents = [
    isCallCenterTeam(team) ? 'Call Center' : null,
    isRcmTeam(team) ? 'RCM' : null,
    isPreApprovalsUaeTeam(team) ? 'Pre-Approvals' : null,
  ].filter(Boolean) as string[];
  return parents.length ? parents : [team];
}

const unique = (values: string[]) => Array.from(new Set(values)).sort();

function matches(record: ScopeRecord, filters: InsightFilters, keys: Array<'region' | 'team' | 'level'>) {
  const team = apiTeamParam(filters);
  return (!keys.includes('region') || !filters.region || record.region === filters.region)
    && (!keys.includes('team') || !team || teamBelongsToFunction(record.team, team))
    && (!keys.includes('level') || !filters.performanceLevel || record.level === filters.performanceLevel);
}

export function scopedInsightOptions(
  records: ScopeRecord[],
  filters: InsightFilters,
  mode: 'pr14' | 'legacy' = 'pr14',
): { options: Pick<InsightOptions, 'periods' | 'regions' | 'teams' | 'performance_levels' | 'functions' | 'team_functions'>; currentPeriod: string | null } {
  const periods = unique(records.map((record) => record.period)).reverse().map(periodFromKey);
  const scoped = records.filter((record) => matches(record, filters, ['region', 'team', 'level']));
  const currentPeriod = filters.periodKey || unique(scoped.map((record) => record.period)).at(-1) || null;
  if (mode === 'legacy') {
    return {
      currentPeriod,
      options: {
        periods,
        regions: unique(records.map((record) => record.region)),
        teams: unique(records.filter((record) => matches(record, filters, ['region'])).map((record) => record.team)),
        performance_levels: unique(records
          .filter((record) => matches(record, filters, ['region', 'team']) && (!filters.periodKey || record.period === filters.periodKey))
          .map((record) => record.level)),
      },
    };
  }
  const inPeriod = records.filter((record) => !currentPeriod || record.period === currentPeriod);
  const narrowed = (keys: Array<'region' | 'team' | 'level'>) => inPeriod.filter((record) => matches(record, filters, keys));
  const teams = unique(narrowed(['region', 'level']).map((record) => record.team));
  return {
    currentPeriod,
    options: {
      periods,
      regions: unique(narrowed(['team', 'level']).map((record) => record.region)),
      teams,
      performance_levels: unique(narrowed(['region', 'team']).map((record) => record.level)),
      functions: unique(narrowed(['region', 'level']).flatMap((record) => functionsForTeam(record.team))),
      team_functions: Object.fromEntries(teams.map((team) => [team, functionsForTeam(team)])),
    },
  };
}
