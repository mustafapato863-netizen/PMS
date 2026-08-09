import type { AgentRecord } from '../../types';
import { normalizeTeamName } from '../../hooks/api/useKpiWeights';

const MONTH_NUMBER: Record<string, number> = {
  January: 1, February: 2, March: 3, April: 4, May: 5, June: 6,
  July: 7, August: 8, September: 9, October: 10, November: 11, December: 12,
};

export function resolveAvailableTeamPeriods(
  agents: AgentRecord[],
  teamName: string | null,
  fallbackYear = new Date().getFullYear(),
) {
  const normalizedTeam = normalizeTeamName(teamName || '');
  const periods = new Map<string, { month: string; year: number }>();
  agents
    .filter((agent) => !teamName || normalizeTeamName(agent.identity.team || '') === normalizedTeam)
    .forEach((agent) => {
      const period = {
        month: agent.identity.month,
        year: agent.year ?? fallbackYear,
      };
      periods.set(`${period.year}-${period.month}`, period);
    });

  return Array.from(periods.values()).sort((left, right) =>
    left.year - right.year || (MONTH_NUMBER[left.month] ?? 0) - (MONTH_NUMBER[right.month] ?? 0)
  );
}
