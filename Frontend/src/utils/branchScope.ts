import type { AgentRecord, LocationKey } from '../types';

/** Source branch fields take precedence over copied geo totals in legacy uploads. */
export function agentMatchesLocation(agent: AgentRecord, location: LocationKey): boolean {
  if (location === 'all') return true;
  if (agent.branch_key?.trim()) return agent.branch_key.trim().toLowerCase() === location;
  const raw = agent.raw_data || {};
  const text = [raw.Team, raw['Out Team'], raw.Branch, raw.Site, raw.Area, agent.identity.team]
    .filter(Boolean).join(' ').toUpperCase();
  const explicitBranch = text.includes('AJM') || text.includes('AJMAN')
    ? 'ajman'
    : text.includes('SHJ') || text.includes('SHARJAH') || text.includes('SHARQA')
      ? 'sharjah'
      : text.includes('DUBAI')
        ? 'dubai'
        : text.includes('CLINIC') ? 'clinics' : undefined;
  if (explicitBranch) return explicitBranch === location;
  return (agent.geo?.bookings?.[location] || 0) > 0 || (agent.geo?.attended?.[location] || 0) > 0;
}
