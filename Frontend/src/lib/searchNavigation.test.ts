import { describe, expect, it } from 'vitest';
import type { User } from '../types';
import { buildLocalSearchResults } from './searchNavigation';

const user = (role: User['role'], hasUnrestrictedTeamAccess = false): User => ({
  id: `${role.toLowerCase().replace(/\s+/g, '-')}-1`,
  name: role,
  username: role.toLowerCase().replace(/\s+/g, '-'),
  role,
  has_unrestricted_team_access: hasUnrestrictedTeamAccess,
  accessible_teams: [],
});

const pathsFor = (currentUser: User) => buildLocalSearchResults({
  role: currentUser.role,
  currentUser,
  firstTeamPath: '/team/marketing',
  query: '',
}).map((item) => item.path);

const SETTINGS_SHORTCUTS = ['/settings?tab=upload', '/settings?tab=users'];
const BROAD_PATHS = ['/reports', '/insights', '/planning'];

describe('buildLocalSearchResults access (General Manager role string)', () => {
  it('lets a General Manager search product pages and Team Management, but not Settings shortcuts', () => {
    const paths = pathsFor(user('General Manager', true));
    for (const path of [...BROAD_PATHS, '/corrective-actions', '/team-management', '/executive', '/departmental-summary', '/team/all']) {
      expect(paths).toContain(path);
    }
    for (const path of SETTINGS_SHORTCUTS) expect(paths).not.toContain(path);
  });

  it('does not treat a Manager with has_unrestricted_team_access as a General Manager', () => {
    const paths = pathsFor(user('Manager', true));
    // Executive v1 (Mustafa): Manager gets Reports, Planning and Corrective Actions, never Insights.
    for (const path of ['/insights', '/team-management', ...SETTINGS_SHORTCUTS]) {
      expect(paths).not.toContain(path);
    }
    for (const path of ['/executive', '/departmental-summary', '/reports', '/planning', '/corrective-actions']) expect(paths).toContain(path);
  });

  it('keeps Settings, user and team management search items for Admin', () => {
    const paths = pathsFor(user('Admin', true));
    for (const path of [...BROAD_PATHS, '/corrective-actions', '/team-management', ...SETTINGS_SHORTCUTS]) {
      expect(paths).toContain(path);
    }
  });

  it('offers Executive Corrective Actions but not Admin/GM-only pages', () => {
    const paths = pathsFor(user('Executive'));
    expect(paths).toContain('/corrective-actions');
    for (const path of [...BROAD_PATHS, '/team-management', ...SETTINGS_SHORTCUTS]) expect(paths).not.toContain(path);
  });

  it('keeps upload and user-management actions Admin-only', () => {
    const ids = (role: User['role']) => buildLocalSearchResults({ role, currentUser: user(role), firstTeamPath: null, query: '' }).map((item) => item.id);
    expect(ids('Admin')).toEqual(expect.arrayContaining(['action-upload-workbook', 'nav-user-management', 'action-manage-team']));
    expect(ids('General Manager')).not.toContain('action-upload-workbook');
    expect(ids('General Manager')).not.toContain('nav-user-management');
    expect(ids('General Manager')).toContain('action-manage-team');
  });

  it('labels the teams workspace "All Teams" for General Managers and "Assigned Teams" for Managers', () => {
    const label = (role: User['role']) => buildLocalSearchResults({ role, currentUser: user(role), firstTeamPath: null, query: 'teams' })
      .find((item) => item.id === 'nav-teams')?.label;
    expect(label('General Manager')).toBe('All Teams');
    expect(label('Manager')).toBe('Assigned Teams');
  });
});

describe('buildLocalSearchResults for Function Viewer', () => {
  it('offers Function Summary and Reports but no Executive Summary or broad pages', () => {
    const paths = pathsFor(user('Function Viewer'));
    expect(paths).toContain('/function-summary');
    expect(paths).toContain('/reports');
    for (const path of ['/executive', '/departmental-summary', '/insights', '/planning', '/corrective-actions', '/team/all', ...SETTINGS_SHORTCUTS]) {
      expect(paths).not.toContain(path);
    }
  });

  it('offers Function Summary to Admin and General Manager, not to Manager or Executive', () => {
    expect(pathsFor(user('Admin', true))).toContain('/function-summary');
    expect(pathsFor(user('General Manager', true))).toContain('/function-summary');
    expect(pathsFor(user('Manager'))).not.toContain('/function-summary');
    expect(pathsFor(user('Executive'))).not.toContain('/function-summary');
  });
});
