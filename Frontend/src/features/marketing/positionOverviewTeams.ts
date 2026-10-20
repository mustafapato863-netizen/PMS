import { TEAM_DB_NAME_MAP, TEAM_NAME_MAP, teamPath } from '../../types';

/** Employee routes that reuse the Marketing position overview. Marketing keeps its own route. */
export const POSITION_OVERVIEW_TEAM_IDS = ['finance', 'human-resources', 'it', 'administration'] as const;

export const isPositionOverviewTeam = (teamId: string | undefined): boolean => (
  Boolean(teamId && (POSITION_OVERVIEW_TEAM_IDS as readonly string[]).includes(teamId))
);

export const isDepartmentManagementLevel = (performanceLevel: string | null) => (
  performanceLevel === 'Managerial' || performanceLevel === 'Corporate'
);

export interface PositionOverviewIdentity {
  teamId: string;
  label: string;
  dbName: string;
  overviewTitle: string;
  overviewPath: string;
}

export const positionOverviewIdentity = (teamId = 'marketing'): PositionOverviewIdentity => {
  const id = TEAM_NAME_MAP[teamId] ? teamId : 'marketing';
  const label = TEAM_NAME_MAP[id] ?? 'Marketing';
  const dbName = TEAM_DB_NAME_MAP[id] ?? label;
  return {
    teamId: id,
    label,
    dbName,
    overviewTitle: `${label} Overview`,
    overviewPath: teamPath(dbName),
  };
};
