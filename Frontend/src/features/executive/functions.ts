import { INSIGHT_FUNCTIONS, teamBelongsToFunction, type TeamFunctionMap } from '../insights/filterCascade';
import type { ExecutiveFunction } from './types';
import { CALL_CENTER_TEAM, PRE_APPROVALS_UAE_TEAM, RCM_TEAM, canonicalTeamName, isCallCenterTeam, isPreApprovalsUaeTeam, isRcmTeam, teamPath } from '../../types';
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
 * - Sales, Pharmacy and CSR are standalone functions with their own cards.
 *   Only teams outside the supported functions return `null`.
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
  Finance: 'finance',
  'Human Resources': 'human-resources',
  IT: 'it',
  Administration: 'administration',
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

/**
 * Parent view a team sits under, only when that parent page shows the team:
 * the UAE workflows (OP/IP Final merged views, IP Elective) under the UAE
 * Pre-Approvals view, Inbound and Outbound under Call Center, other RCM teams
 * under RCM. Pre-Approvals IP Offshore is not on the UAE parent page, so it has
 * no Pre-Approvals crumb. Parent views and stand-alone teams have none.
 */
export function parentTeamView(team: string | null | undefined): string | null {
  const name = canonicalTeamName(team);
  if (!name || name === PRE_APPROVALS_UAE_TEAM || name === CALL_CENTER_TEAM || name === RCM_TEAM) return null;
  if (isPreApprovalsUaeTeam(name)) return PRE_APPROVALS_UAE_TEAM;
  if (isCallCenterTeam(name)) return CALL_CENTER_TEAM;
  if (isRcmTeam(name)) return RCM_TEAM;
  return null;
}

export interface TeamBreadcrumb {
  label: string;
  href?: string;
  icon?: 'home' | 'teams' | 'team';
}

/**
 * Executive Summary > Function > Team or parent view > Sub-team. The function
 * crumb opens the Function Summary when `canOpenFunctionSummary`, otherwise the
 * Executive Summary filtered to that function. A crumb that would repeat the
 * name above it (RCM, Call Center, Sales) is left out. `team` is the resolved
 * team name, or null for the all-teams view.
 */
export function teamBreadcrumbs({ team, displayName, canOpenFunctionSummary, allTeamsHref }: {
  team: string | null;
  displayName: string;
  canOpenFunctionSummary: boolean;
  allTeamsHref: string;
}): TeamBreadcrumb[] {
  const summary: TeamBreadcrumb = { label: 'Executive Summary', href: '/executive', icon: 'home' };
  if (!team) return [summary, { label: 'Team Performance', href: allTeamsHref, icon: 'teams' }];
  const crumbs: TeamBreadcrumb[] = [summary];
  const fn = executiveFunctionForTeam(team);
  const parent = parentTeamView(team);
  if (fn && fn !== canonicalTeamName(team)) {
    crumbs.push({
      label: fn,
      href: canOpenFunctionSummary ? `/function-summary/${functionSlug(fn)}` : `/executive?function=${encodeURIComponent(fn)}`,
    });
  }
  if (parent && parent !== fn) crumbs.push({ label: parent, href: teamPath(parent) });
  crumbs.push({ label: displayName, icon: 'team' });
  return crumbs;
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
