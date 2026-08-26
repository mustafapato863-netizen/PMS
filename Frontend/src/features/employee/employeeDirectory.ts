import { sameCanonicalTeam } from '../../types';
import type { TeamAgentRow } from '../../hooks/usePerformanceData';

export const ALL_EMPLOYEE_POSITIONS = 'All positions';

export function getEmployeeDirectoryPosition(row: TeamAgentRow): string {
  const raw = row.raw;
  const position = raw.position || raw.identity.position || raw.raw_data?.Position || raw.raw_data?.position;
  return String(position || '').trim() || 'Unassigned';
}

export function getEmployeeDirectoryRows(
  rows: TeamAgentRow[],
  teamFilter: string,
  positionFilter: string,
): TeamAgentRow[] {
  return rows
    .filter((row) => (
      (!teamFilter || sameCanonicalTeam(row.team, teamFilter))
      && (positionFilter === ALL_EMPLOYEE_POSITIONS || getEmployeeDirectoryPosition(row) === positionFilter)
    ))
    .slice()
    .sort((left, right) => left.name.localeCompare(right.name));
}

export function getEmployeeDirectoryTeams(rows: TeamAgentRow[]): string[] {
  const teams = new Map<string, string>();
  rows.forEach((row) => {
    const team = String(row.team || '').trim();
    if (team) teams.set(team.toLocaleLowerCase(), team);
  });
  return Array.from(teams.values()).sort((left, right) => left.localeCompare(right));
}

export function getEmployeeDirectoryPositions(rows: TeamAgentRow[], teamFilter: string): string[] {
  const positions = new Set(
    getEmployeeDirectoryRows(rows, teamFilter, ALL_EMPLOYEE_POSITIONS)
      .map(getEmployeeDirectoryPosition),
  );
  return Array.from(positions).sort((left, right) => left.localeCompare(right));
}
