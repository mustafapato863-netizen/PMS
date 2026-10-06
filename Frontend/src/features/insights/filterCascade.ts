import type { InsightOptions, InsightFilters } from './types';
import {
  canonicalTeamName,
  isCallCenterTeam,
  isPreApprovalsUaeTeam,
  isRcmTeam,
} from '../../types';

/**
 * Header "Functions" are the parent domains the backend already understands
 * as `team` values: `Backend/utils/report_scope.py::_team_keys` expands
 * Call Center / RCM / Pre-Approvals to their source teams, and any other value
 * (Marketing) is an exact team match. This list is unchanged from the
 * previous Function filter.
 */
export const INSIGHT_FUNCTIONS = ['Call Center', 'RCM', 'Pre-Approvals', 'Marketing'] as const;

const identity = (value: string | null | undefined) => canonicalTeamName(value).toLowerCase();

/**
 * Team → function membership reuses the existing team-family helpers in
 * `src/types.ts`, which mirror the backend `_team_keys` sets
 * (Call Center = Call Center/Inbound/Outbound; RCM = RCM, Coding, Submission,
 * Re-Submission and every Pre-Approvals team incl. IP Offshore;
 * Pre-Approvals = UAE pre-approvals only). No new mapping is introduced.
 */
export function teamBelongsToFunction(team: string, teamFunction: string): boolean {
  switch (identity(teamFunction)) {
    case 'call center':
      return isCallCenterTeam(team);
    case 'rcm':
      return isRcmTeam(team);
    case 'pre-approvals':
      return isPreApprovalsUaeTeam(team);
    default:
      return identity(team) === identity(teamFunction);
  }
}

function uniqueCanonical(teams: string[]): string[] {
  const seen = new Map<string, string>();
  teams.forEach((team) => {
    const name = canonicalTeamName(team);
    if (name && !seen.has(name.toLowerCase())) seen.set(name.toLowerCase(), name);
  });
  return Array.from(seen.values()).sort((left, right) => left.localeCompare(right));
}

/**
 * Teams available for the header Teams dropdown. `apiTeams` is
 * `workspace.options.teams`, which the API scopes to the selected region and
 * the caller's authorized records. Membership is tested on the source team
 * names first, then merged branch teams are collapsed to their canonical name.
 */
export function teamOptionsFor(apiTeams: string[], teamFunction?: string): string[] {
  const scoped = teamFunction ? apiTeams.filter((team) => teamBelongsToFunction(team, teamFunction)) : apiTeams;
  return uniqueCanonical(scoped);
}

/** Functions that still have at least one team in the API-provided scope. */
export function functionOptionsFor(apiTeams: string[]): string[] {
  return INSIGHT_FUNCTIONS.filter((teamFunction) => apiTeams.some((team) => teamBelongsToFunction(team, teamFunction)));
}

/** The API's `team` param: a selected team is always a subset of its function. */
export function apiTeamParam(filters: Pick<InsightFilters, 'team' | 'teamFunction'>): string | undefined {
  return filters.team || filters.teamFunction || undefined;
}

const includesValue = (values: string[], value: string) => values.some((item) => item.toLowerCase() === value.toLowerCase());

/**
 * Clear header selections that the current API option lists no longer
 * support. Upstream selections are validated first; when one is cleared the
 * downstream ones are left for the next response, because the API computed
 * their option lists against the now-invalid upstream value.
 */
export function reconcileCascade(
  filters: InsightFilters,
  options: Pick<InsightOptions, 'regions' | 'teams' | 'performance_levels'>,
): InsightFilters | null {
  const cleared: Partial<Record<keyof InsightFilters, undefined>> = {};
  if (filters.region && !includesValue(options.regions, filters.region)) {
    cleared.region = undefined;
  } else if (filters.teamFunction && !includesValue(functionOptionsFor(options.teams), filters.teamFunction)) {
    // A team is always a subset of its function, so it goes with it.
    Object.assign(cleared, { teamFunction: undefined, team: undefined });
  } else if (filters.team && !includesValue(teamOptionsFor(options.teams, filters.teamFunction), canonicalTeamName(filters.team))) {
    cleared.team = undefined;
  } else if (filters.performanceLevel && !includesValue(options.performance_levels, filters.performanceLevel)) {
    cleared.performanceLevel = undefined;
  }
  if (!Object.keys(cleared).length) return null;
  return { ...filters, ...cleared, position: undefined, employeeId: undefined, kpi: undefined };
}
