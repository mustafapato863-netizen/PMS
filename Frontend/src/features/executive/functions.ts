import { INSIGHT_FUNCTIONS, teamBelongsToFunction, type TeamFunctionMap } from '../insights/filterCascade';
import type { ExecutiveFunction } from './types';
import { isPreApprovalsUaeTeam } from '../../types';

const IP_OFFSHORE_TEAM = 'Pre-Approvals IP Offshore';
const normalizeTeamIdentity = (value: string | null | undefined) => String(value ?? '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '');

/** The four executive functions, in the fixed display order (same as the Insights header). */
export const EXECUTIVE_FUNCTIONS: readonly ExecutiveFunction[] = INSIGHT_FUNCTIONS;

/**
 * Disjoint team → function mapping for the Executive / Function Summary cards
 * ONLY (CoS decision). Insights keeps its overlapping membership.
 *
 * - UAE Pre-Approvals teams (OP / IP Final / IP Elective) → Pre-Approvals,
 *   even though backend `team_functions` also lists them under RCM.
 * - Pre-Approvals IP Offshore → RCM (Mustafa).
 * - Otherwise the backend `team_functions` map (PR #14) or the existing
 *   frontend helpers decide, so CSR is not under Call Center (it is its own
 *   function in the backend; flagged as a design/data difference).
 * - Teams outside the four (Sales, Pharmacy, CSR, …) return `null`: they count
 *   in the company score but get no function card.
 */
export function executiveFunctionForTeam(team: string | null | undefined, teamFunctions?: TeamFunctionMap): ExecutiveFunction | null {
  if (!team) return null;
  // Explicit rules first so a backend map listing a team under both functions cannot override them.
  if (normalizeTeamIdentity(team) === normalizeTeamIdentity(IP_OFFSHORE_TEAM)) return 'RCM';
  if (isPreApprovalsUaeTeam(team) || teamBelongsToFunction(team, 'Pre-Approvals', teamFunctions)) return 'Pre-Approvals';
  for (const name of ['Call Center', 'RCM', 'Marketing'] as const) {
    if (teamBelongsToFunction(team, name, teamFunctions)) return name;
  }
  return null;
}

const SLUGS: Record<ExecutiveFunction, string> = {
  'Call Center': 'call-center',
  RCM: 'rcm',
  'Pre-Approvals': 'pre-approvals',
  Marketing: 'marketing',
};

export function functionSlug(name: ExecutiveFunction): string {
  return SLUGS[name];
}

export function functionFromSlug(slug: string | null | undefined): ExecutiveFunction | null {
  const normalized = String(slug ?? '').trim().toLowerCase();
  return EXECUTIVE_FUNCTIONS.find((name) => SLUGS[name] === normalized || name.toLowerCase() === normalized) ?? null;
}

export function isExecutiveFunction(value: string | null | undefined): value is ExecutiveFunction {
  return EXECUTIVE_FUNCTIONS.some((name) => name === value);
}
