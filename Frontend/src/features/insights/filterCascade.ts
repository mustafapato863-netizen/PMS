import type { InsightOptions, InsightFilters } from './types';
import {
  MERGED_IP_FINAL_SOURCE_TEAMS,
  MERGED_IP_FINAL_TEAM,
  MERGED_OP_FINAL_SOURCE_TEAMS,
  MERGED_OP_FINAL_TEAM,
  canonicalTeamName,
  isCallCenterTeam,
  isPreApprovalsUaeTeam,
  isRcmTeam,
} from '../../types';

/**
 * The header Functions list is fixed to these four parent domains (Mustafa's
 * decision on PR #13), in this order. A function is hidden only when the
 * current option scope has none of its teams. The backend (PR #14) may list
 * more `options.functions` (standalone teams such as Sales or CSR are their
 * own function there); those are never shown here.
 */
export const INSIGHT_FUNCTIONS = ['Call Center', 'RCM', 'Pre-Approvals', 'Marketing'] as const;

/** `options.team_functions` from PR #14: source team name → every function it rolls up into. */
export type TeamFunctionMap = Record<string, string[]>;

type CascadeOptions = Pick<InsightOptions, 'regions' | 'teams' | 'performance_levels' | 'functions' | 'team_functions'>;

const identity = (value: string | null | undefined) => canonicalTeamName(value).trim().toLowerCase();

/** Merged branch teams are shown by their canonical name; membership is defined on the source names. */
function sourceNames(team: string): string[] {
  const canonical = canonicalTeamName(team);
  if (canonical === MERGED_OP_FINAL_TEAM) return [team, MERGED_OP_FINAL_TEAM, ...MERGED_OP_FINAL_SOURCE_TEAMS];
  if (canonical === MERGED_IP_FINAL_TEAM) return [team, MERGED_IP_FINAL_TEAM, ...MERGED_IP_FINAL_SOURCE_TEAMS];
  return [team];
}

function mappedFunctions(team: string, teamFunctions: TeamFunctionMap | undefined): string[] | null {
  if (!teamFunctions) return null;
  const keys = Object.keys(teamFunctions);
  const matches = sourceNames(team).flatMap((name) => {
    const key = keys.find((candidate) => candidate === name)
      ?? keys.find((candidate) => candidate.trim().toLowerCase() === name.trim().toLowerCase());
    return key ? teamFunctions[key] : [];
  });
  return matches.length ? matches : null;
}

/**
 * Fallback when the API has no `team_functions` (backend without PR #14):
 * the existing team-family helpers in `src/types.ts`, which mirror backend
 * `report_scope._team_keys` (Call Center = Call Center/Inbound/Outbound;
 * RCM = RCM, Coding, Submission, Re-Submission and every Pre-Approvals team
 * incl. IP Offshore; Pre-Approvals = UAE pre-approvals only).
 */
function helperBelongs(team: string, teamFunction: string): boolean {
  return sourceNames(team).some((name) => {
    switch (identity(teamFunction)) {
      case 'call center':
        return isCallCenterTeam(name);
      case 'rcm':
        return isRcmTeam(name);
      case 'pre-approvals':
        return isPreApprovalsUaeTeam(name);
      default:
        return identity(name) === identity(teamFunction);
    }
  });
}

/**
 * Team → function membership. `options.team_functions` (PR #14) wins when the
 * response has it; a team may map to several functions (UAE Pre-Approvals
 * teams are `["RCM", "Pre-Approvals"]`) and is then listed under each.
 */
export function teamBelongsToFunction(team: string, teamFunction: string, teamFunctions?: TeamFunctionMap): boolean {
  const mapped = mappedFunctions(team, teamFunctions);
  if (mapped) return mapped.some((name) => identity(name) === identity(teamFunction));
  return helperBelongs(team, teamFunction);
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
 * Teams for the header Teams dropdown: `options.teams` (scoped by the API to
 * the region, and with PR #14 also to the level and the current period),
 * narrowed to the selected function on the source names, then merged branch
 * teams collapsed to their canonical name.
 */
export function teamOptionsFor(apiTeams: string[], teamFunction?: string, teamFunctions?: TeamFunctionMap): string[] {
  const scoped = teamFunction
    ? apiTeams.filter((team) => teamBelongsToFunction(team, teamFunction, teamFunctions))
    : apiTeams;
  return uniqueCanonical(scoped);
}

/**
 * The fixed four functions, in fixed order, minus any with no data in scope.
 *
 * With PR #14 this is `options.functions` (computed ignoring both the team and
 * the function selection, so the other functions stay listed and the user can
 * switch directly between them) intersected with the fixed four. It must not
 * be derived from `options.teams`: since PR #17 sends `function=`, the backend
 * narrows `teams` to the selected function (QA BUG-5). Older APIs without
 * `options.functions` fall back to the functions that have a team in
 * `options.teams` (not narrowed by function there).
 */
export function functionOptionsFor(options: Pick<CascadeOptions, 'teams' | 'functions' | 'team_functions'>): string[] {
  if (Array.isArray(options.functions)) {
    const apiFunctions = new Set(options.functions.map((name) => identity(name)));
    return INSIGHT_FUNCTIONS.filter((teamFunction) => apiFunctions.has(identity(teamFunction)));
  }
  return INSIGHT_FUNCTIONS.filter((teamFunction) => (
    options.teams.some((team) => teamBelongsToFunction(team, teamFunction, options.team_functions))
  ));
}

/**
 * Single `team` value for endpoints without a `function` param (report export,
 * quick-action team data). A selected team is always a subset of its function,
 * and the backend expands a function name to its source teams.
 */
export function apiTeamParam(filters: Pick<InsightFilters, 'team' | 'teamFunction'>): string | undefined {
  return filters.team || filters.teamFunction || undefined;
}

const includesValue = (values: string[], value: string) => values.some((item) => item.toLowerCase() === value.toLowerCase());

/**
 * Clear header selections the current API option lists no longer support.
 *
 * With PR #14 every list is faceted (it ignores only its own filter), so in a
 * contradictory combination several lists can disagree at once. To keep the
 * Region → Function → Team → Level cascade, the most upstream selection the
 * user made is kept and the downstream ones are cleared first; Region is only
 * cleared when it is the culprit (no teams at all, or everything downstream is
 * valid). One selection is cleared per response; the next response re-checks.
 */
export function reconcileCascade(filters: InsightFilters, options: CascadeOptions): InsightFilters | null {
  const teamFunctions = options.team_functions;
  const regionInvalid = Boolean(filters.region && !includesValue(options.regions, filters.region));
  const functionInvalid = Boolean(filters.teamFunction && !includesValue(functionOptionsFor(options), filters.teamFunction));
  const teamInvalid = Boolean(filters.team
    && !includesValue(teamOptionsFor(options.teams, filters.teamFunction, teamFunctions), canonicalTeamName(filters.team)));
  const levelInvalid = Boolean(filters.performanceLevel && !includesValue(options.performance_levels, filters.performanceLevel));
  // No teams at all means the region (or, with PR #14, the level) has no data
  // in this period, so team-dimension checks are inconclusive. Likewise an
  // empty level list means the team/function itself has no data, so a level
  // mismatch is not the level's fault.
  const teamsEmpty = options.teams.length === 0;
  const levelsEmpty = options.performance_levels.length === 0;

  // Since PR #17 `teams` is also narrowed by the function, so an empty team
  // list only blames the region when the API's function list (which ignores
  // the function) does not show the selected function as the culprit.
  const functionIsCulprit = functionInvalid && Array.isArray(options.functions) && options.functions.length > 0;

  const cleared: Partial<Record<keyof InsightFilters, undefined>> = {};
  if (teamsEmpty && regionInvalid && !functionIsCulprit) {
    cleared.region = undefined;
  } else if (levelInvalid && !levelsEmpty && (teamsEmpty || teamInvalid || functionInvalid)) {
    // PR #14 narrows teams by level: the team/function has data here, just
    // not at this level, so the downstream level is what goes.
    cleared.performanceLevel = undefined;
  } else if (functionInvalid) {
    // A team is always a subset of its function, so it goes with it.
    Object.assign(cleared, { teamFunction: undefined, team: undefined });
  } else if (teamInvalid) {
    cleared.team = undefined;
  } else if (levelInvalid) {
    cleared.performanceLevel = undefined;
  } else if (regionInvalid) {
    cleared.region = undefined;
  }
  if (!Object.keys(cleared).length) return null;
  return { ...filters, ...cleared, position: undefined, employeeId: undefined, kpi: undefined };
}
