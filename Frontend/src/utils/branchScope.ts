import type { AgentRecord, LocationKey } from '../types';

/**
 * Branch named by the source text of a row, in the server's fixed order
 * (`text_branch` in utils/branch_scope.py). Raw Team, Out Team, Branch, Site and
 * Area are read first; the team name only contributes Dubai, and only when the
 * raw text names no other branch.
 */
function textBranch(agent: AgentRecord): LocationKey | undefined {
  const raw = agent.raw_data || {};
  const text = ['Team', 'Out Team', 'Branch', 'Site', 'Area']
    .map((field) => String((raw as Record<string, unknown>)[field] ?? ''))
    .filter(Boolean).join(' ').toUpperCase();
  const team = String(agent.identity?.team ?? '').toUpperCase();
  if (text.includes('AJM') || text.includes('AJMAN')) return 'ajman';
  if (text.includes('SHJ') || text.includes('SHARJAH') || text.includes('SHARQA')) return 'sharjah';
  if (text.includes('DUBAI') || team.includes('DUBAI')) return 'dubai';
  if (text.includes('CLINIC')) return 'clinics';
  return undefined;
}

/**
 * The one branch rule (utils/branch_scope.py `record_matches_branch`): the stored
 * branch_key when the row has one; otherwise the source text; otherwise the row's
 * geo bookings or attendance for that branch.
 */
export function agentMatchesLocation(agent: AgentRecord, location: LocationKey): boolean {
  if (location === 'all') return true;
  const stored = agent.branch_key?.trim().toLowerCase();
  if (stored) return stored === location;
  const explicit = textBranch(agent);
  if (explicit) return explicit === location;
  return (agent.geo?.bookings?.[location] || 0) > 0 || (agent.geo?.attended?.[location] || 0) > 0;
}
