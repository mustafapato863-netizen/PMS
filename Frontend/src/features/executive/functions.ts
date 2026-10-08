import { INSIGHT_FUNCTIONS, teamBelongsToFunction, type TeamFunctionMap } from '../insights/filterCascade';
import type { ExecutiveFunction } from './types';
import { canonicalTeamName, isPreApprovalsUaeTeam } from '../../types';
import { isFunctionViewerRole } from '../../lib/access';

const IP_OFFSHORE_TEAM = 'Pre-Approvals IP Offshore';
const normalizeTeamIdentity = (value: string | null | undefined) => String(value ?? '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '');

/** Current functions; Pre-Approvals is an RCM team, not a function choice. */
export const EXECUTIVE_FUNCTIONS: readonly ExecutiveFunction[] = INSIGHT_FUNCTIONS;

/** Selection hierarchy only. Never use this broader rollup to infer authorization. */
export function isPreApprovalsSubTeam(team: string | null | undefined): boolean {
  return isPreApprovalsUaeTeam(team) || normalizeTeamIdentity(team) === normalizeTeamIdentity(IP_OFFSHORE_TEAM);
}

export function summaryTeamMatches(team: string, selected: string): boolean {
  return selected === 'Pre-Approvals' ? isPreApprovalsSubTeam(team) : canonicalTeamName(team) === canonicalTeamName(selected);
}

export function summaryTeamOptions(teams: string[]): string[] {
  return [...new Set(teams.map((team) => isPreApprovalsSubTeam(team) ? 'Pre-Approvals' : canonicalTeamName(team)))].sort((a, b) => a.localeCompare(b));
}

export function preApprovalsSubTeamOptions(teams: string[]): string[] {
  return [...new Set(teams.filter((team) => isPreApprovalsSubTeam(team) && team !== 'Pre-Approvals').map(canonicalTeamName))].sort((a, b) => a.localeCompare(b));
}

/**
 * Pre-Approvals workflows (UAE and Offshore) belong to RCM. Legacy backend
 * Pre-Approvals membership is kept only to preserve restricted old grants.
 * - Otherwise the backend `team_functions` map (PR #14) or the existing
 *   frontend helpers decide, so CSR is not under Call Center (it is its own
 *   function in the backend; flagged as a design/data difference).
 * - Teams outside the current functions (Sales, Pharmacy, CSR, …) return `null`: they count
 *   in the company score but get no function card.
 */
export function executiveFunctionForTeam(team: string | null | undefined, teamFunctions?: TeamFunctionMap): ExecutiveFunction | null {
  if (!team) return null;
  // Explicit rules first so a backend map listing a team under both functions cannot override them.
  if (normalizeTeamIdentity(team) === normalizeTeamIdentity(IP_OFFSHORE_TEAM)) return 'RCM';
  if (isPreApprovalsSubTeam(team) || teamBelongsToFunction(team, 'Pre-Approvals', teamFunctions)) return 'RCM';
  for (const name of EXECUTIVE_FUNCTIONS) {
    if (teamBelongsToFunction(team, name, teamFunctions)) return name;
  }
  return null;
}

export function summaryFunctionMatches(team: string, fn: string, teamFunctions?: TeamFunctionMap): boolean {
  return fn === 'Pre-Approvals'
    ? teamBelongsToFunction(team, fn)
    : executiveFunctionForTeam(team, teamFunctions) === fn;
}

const SLUGS: Record<ExecutiveFunction, string> = {
  'Call Center': 'call-center',
  RCM: 'rcm',
  'Pre-Approvals': 'pre-approvals',
  Marketing: 'marketing',
  Sales: 'sales',
  CSR: 'csr',
  Pharmacy: 'pharmacy',
};

export function functionSlug(name: ExecutiveFunction): string {
  return SLUGS[name];
}

export function functionFromSlug(slug: string | null | undefined): ExecutiveFunction | null {
  const normalized = String(slug ?? '').trim().toLowerCase();
  return [...EXECUTIVE_FUNCTIONS, 'Pre-Approvals' as const].find((name) => SLUGS[name] === normalized || name.toLowerCase() === normalized) ?? null;
}

export function isExecutiveFunction(value: string | null | undefined): value is ExecutiveFunction {
  return EXECUTIVE_FUNCTIONS.some((name) => name === value);
}

/** Team dashboard path, same slug rule as the sidebar team links. */
export function teamPath(team: string): string {
  return `/team/${team.trim().toLowerCase().replace(/&/g, 'and').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')}`;
}

/**
 * Functions a viewer may open on the Function Summary. Admin / GM: all current functions.
 * Function Viewer: only the functions explicitly returned in /auth/me; an empty
 * or missing assignment grants no function access.
 */
export function allowedFunctionsFor(role: string | null | undefined, accessibleFunctions?: string[]): ExecutiveFunction[] {
  if (!isFunctionViewerRole(role)) return [...EXECUTIVE_FUNCTIONS];
  const wanted = new Set((accessibleFunctions ?? []).map((name) => name.trim().toLowerCase()));
  // Retain old narrow grants; never translate them to a broader RCM permission.
  return [...EXECUTIVE_FUNCTIONS, 'Pre-Approvals' as const].filter((fn) => wanted.has(fn.toLowerCase()));
}

/**
 * Function Viewer page scope (team dashboard / employee profile). Lenient on
 * purpose: a team is in scope when its disjoint executive function OR any
 * backend `team_functions` membership matches an allowed function (so an RCM
 * viewer can still open a UAE Pre-Approvals team the backend lists under RCM).
 * The backend must enforce the same rule on the data endpoints.
 */
export function isTeamInFunctions(team: string | null | undefined, allowed: readonly ExecutiveFunction[], teamFunctions?: TeamFunctionMap): boolean {
  if (!team) return false;
  if (allowed.includes('Pre-Approvals') && isPreApprovalsUaeTeam(team)) return true;
  // Legacy Pre-Approvals grants excluded Offshore, even if an old map says otherwise.
  const canonicalAllowed: readonly ExecutiveFunction[] = allowed.filter((fn) => fn !== 'Pre-Approvals');
  const primary = executiveFunctionForTeam(team, teamFunctions);
  if (primary && canonicalAllowed.includes(primary)) return true;
  return canonicalAllowed.some((fn) => teamBelongsToFunction(team, fn, teamFunctions));
}
