import { TEAM_ID_MAP, type User } from '../types';
import {
  canAccessCorrectiveActions,
  canAccessInsights,
  canAccessPlanning,
  canSeeReportsNav,
  canAccessSettingsContent,
  canAccessTeamManagement,
} from './access';

export type SearchGroupId = 'navigation' | 'employees' | 'teams' | 'actions';
export type SearchIconKey =
  | 'search'
  | 'layout'
  | 'team'
  | 'employee'
  | 'settings'
  | 'planning'
  | 'upload'
  | 'shield'
  | 'chart'
  | 'briefcase';

export interface SearchResultItem {
  id: string;
  group: SearchGroupId;
  label: string;
  subtitle: string;
  icon: SearchIconKey;
  path: string;
}

export interface GlobalSearchEmployee {
  id: string;
  name: string;
  employee_id: string;
  team: string;
  performance_level: string;
}

export interface GlobalSearchTeam {
  name: string;
  subtitle: string;
}

export interface GlobalSearchResponse {
  query: string;
  teams: GlobalSearchTeam[];
  employees: GlobalSearchEmployee[];
}

const slugifyTeam = (value: string) =>
  value
    .trim()
    .toLowerCase()
    .replace(/&/g, 'and')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');

const normalizeTeam = (value: string) =>
  value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();

export const buildTeamPath = (teamName: string) => {
  const known = Object.entries(TEAM_ID_MAP).find(([name]) => normalizeTeam(name) === normalizeTeam(teamName));
  return `/team/${known?.[1] || slugifyTeam(teamName)}`;
};

const includesQuery = (value: string, query: string) => value.toLowerCase().includes(query.toLowerCase());

const baseNavigation = ({
  role,
  currentUser,
  firstTeamPath,
}: {
  role: User['role'];
  currentUser: User | null;
  firstTeamPath: string | null;
}): SearchResultItem[] => {
  const items: SearchResultItem[] = [];

  if (role === 'Admin' || role === 'General Manager' || role === 'Manager' || role === 'Executive') {
    items.push({
      id: 'nav-executive',
      group: 'navigation',
      label: 'Executive Summary',
      subtitle: 'Performance overview across all teams',
      icon: 'layout',
      path: '/executive',
    });
  }

  // Same visibility as the sidebar and the RouteGuards (access.ts): Reports and
  // Planning for Admin / General Manager / Manager, Insights for Admin / GM only.
  if (canSeeReportsNav(role)) {
    items.push({
      id: 'nav-reports',
      group: 'navigation',
      label: 'Reports',
      subtitle: 'Reports center, story builder and generated files',
      icon: 'chart',
      path: '/reports',
    });
  }
  if (canAccessInsights(role)) {
    items.push({
      id: 'nav-insights',
      group: 'navigation',
      label: 'Insights',
      subtitle: 'Evidence-based risks, opportunities and performance drivers',
      icon: 'planning',
      path: '/insights',
    });
  }
  if (canAccessPlanning(role)) {
    items.push({ id: 'nav-planning', group: 'navigation', label: 'Planning', subtitle: 'Create and track measurable performance plans', icon: 'planning', path: '/planning' });
  }

  if (canAccessCorrectiveActions(role)) {
    items.push({
      id: 'nav-corrective-actions',
      group: 'navigation',
      label: 'Corrective Actions',
      subtitle: 'Review and follow up corrective actions',
      icon: 'shield',
      path: '/corrective-actions',
    });
  }

  if (role === 'Admin' || role === 'General Manager' || role === 'Manager') {
    items.push({
      id: 'nav-teams',
      group: 'navigation',
      label: role === 'Manager' ? 'Assigned Teams' : 'All Teams',
      subtitle: 'Team performance workspace',
      icon: 'team',
      path: '/team/all',
    });
  }

  if (firstTeamPath) {
    items.push({
      id: 'nav-team-dashboard',
      group: 'navigation',
      label: 'Team Dashboard',
      subtitle: 'Open a team performance workspace',
      icon: 'chart',
      path: firstTeamPath,
    });
  }

  if (currentUser?.employee_id || currentUser?.id) {
    items.push({
      id: 'nav-employee-profile',
      group: 'navigation',
      label: 'Employee Profile',
      subtitle: 'Open an employee performance profile',
      icon: 'employee',
      path: `/employee/${currentUser.employee_id || currentUser.id}`,
    });
  }



  // Settings shortcuts are Admin-only (design §6.4). Non-Admins, General Manager included,
  // still reach the soft-locked Settings page from the sidebar.
  if (canAccessSettingsContent(role)) {
    items.push({
      id: 'nav-settings',
      group: 'navigation',
      label: 'Settings',
      subtitle: 'System configuration and uploads',
      icon: 'settings',
      path: '/settings?tab=upload',
    });
  }

  if (canAccessTeamManagement(role)) {
    items.push({
      id: 'nav-team-management',
      group: 'navigation',
      label: 'Team Management',
      subtitle: 'Manage team setup and onboarding',
      icon: 'briefcase',
      path: '/team-management',
    });
  }

  if (canAccessSettingsContent(role)) {
    items.push({
      id: 'nav-user-management',
      group: 'navigation',
      label: 'User Management',
      subtitle: 'Manage users and access roles',
      icon: 'shield',
      path: '/settings?tab=users',
    });
  }

  return items;
};

const baseActions = ({
  role,
  firstTeamPath,
}: {
  role: User['role'];
  firstTeamPath: string | null;
}): SearchResultItem[] => {
  const items: SearchResultItem[] = [];

  if (canAccessSettingsContent(role)) {
    items.push({
      id: 'action-upload-workbook',
      group: 'actions',
      label: 'Upload Performance Workbook',
      subtitle: 'Data ingestion workflow',
      icon: 'upload',
      path: '/settings?tab=upload',
    });
  }



  if (firstTeamPath && role !== 'Agent') {
    items.push({
      id: 'action-management-overview',
      group: 'actions',
      label: 'View Management Overview',
      subtitle: 'Management team dashboard',
      icon: 'briefcase',
      path: `${firstTeamPath}?performance_level=Corporate`,
    });
    items.push({
      id: 'action-balanced-scorecard',
      group: 'actions',
      label: 'Open Balanced Scorecard',
      subtitle: 'Managerial scorecard workspace',
      icon: 'chart',
      path: `${firstTeamPath}?performance_level=Managerial`,
    });
  }

  if (canAccessTeamManagement(role)) {
    items.push({
      id: 'action-manage-team',
      group: 'actions',
      label: 'Create or Manage Team',
      subtitle: 'Team management workspace',
      icon: 'shield',
      path: '/team-management',
    });
  }

  return items;
};

export function buildLocalSearchResults({
  role,
  currentUser,
  firstTeamPath,
  query,
}: {
  role: User['role'];
  currentUser: User | null;
  firstTeamPath: string | null;
  query: string;
}) {
  const normalizedQuery = query.trim().toLowerCase();
  const items = [
    ...baseNavigation({ role, currentUser, firstTeamPath }),
    ...baseActions({ role, firstTeamPath }),
  ];

  if (!normalizedQuery) {
    return items;
  }

  return items.filter((item) => (
    includesQuery(item.label, normalizedQuery) || includesQuery(item.subtitle, normalizedQuery)
  ));
}

export function buildRemoteSearchResults(data: GlobalSearchResponse): SearchResultItem[] {
  return [
    ...data.employees.map((employee) => ({
      id: `employee-${employee.employee_id}`,
      group: 'employees' as const,
      label: employee.name,
      subtitle: `${employee.team} · ${employee.employee_id}`,
      icon: 'employee' as const,
      path: `/employee/${employee.employee_id}`,
    })),
    ...data.teams.map((team) => ({
      id: `team-${team.name}`,
      group: 'teams' as const,
      label: team.name,
      subtitle: team.subtitle,
      icon: 'team' as const,
      path: buildTeamPath(team.name),
    })),
  ];
}
