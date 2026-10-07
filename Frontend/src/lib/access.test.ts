import { describe, expect, it } from 'vitest';
import {
  ROLE_GENERAL_MANAGER,
  USER_ROLE_OPTIONS,
  canAccessBroadAppPages,
  canAccessCorrectiveActions,
  canAccessRoute,
  canAccessSettings,
  canAccessSettingsContent,
  canAccessTeamManagement,
  getRoleDisplayLabel,
  hasAllTeamsScope,
  isAdminRole,
  isGeneralManagerRole,
  readHasUnrestrictedTeamAccess,
} from './access';

describe('access helpers (current roles and legacy transition)', () => {
  it('offers only current roles for new assignments while preserving legacy role identity', () => {
    expect(ROLE_GENERAL_MANAGER).toBe('General Manager');
    expect(USER_ROLE_OPTIONS).toEqual([
      'Admin', 'Manager', 'Employee', 'Performance Team',
      'Regional Manager', 'Branch Director', 'Function Director',
    ]);
    expect(USER_ROLE_OPTIONS).not.toContain('General Manager');
    expect(USER_ROLE_OPTIONS).not.toContain('Function Viewer');
  });

  it('identifies Admin and General Manager by role string only', () => {
    expect(isAdminRole('Admin')).toBe(true);
    expect(isAdminRole('General Manager')).toBe(false);
    expect(isGeneralManagerRole('General Manager')).toBe(true);
    expect(isGeneralManagerRole('Manager')).toBe(false);
    expect(isGeneralManagerRole(null)).toBe(false);
  });

  it('opens broad product pages to Admin, transitional General Manager, and Performance Team', () => {
    expect(canAccessBroadAppPages('Admin')).toBe(true);
    expect(canAccessBroadAppPages('General Manager')).toBe(true);
    expect(canAccessBroadAppPages('Performance Team')).toBe(true);
    for (const role of ['Manager', 'Employee', 'Regional Manager', 'Branch Director', 'Function Director', 'Executive', 'Viewer', 'Agent', undefined]) {
      expect(canAccessBroadAppPages(role)).toBe(false);
    }
  });

  it('opens Corrective Actions to Admin, Executive, General Manager and Manager (Executive v1)', () => {
    expect(canAccessCorrectiveActions('Admin')).toBe(true);
    expect(canAccessCorrectiveActions('Executive')).toBe(true);
    expect(canAccessCorrectiveActions('General Manager')).toBe(true);
    expect(canAccessCorrectiveActions('Manager')).toBe(true);
    expect(canAccessCorrectiveActions('Function Viewer')).toBe(false);
    expect(canAccessCorrectiveActions('Function Director')).toBe(true);
    expect(canAccessCorrectiveActions('Branch Director')).toBe(true);
    expect(canAccessCorrectiveActions('Regional Manager')).toBe(true);
    expect(canAccessCorrectiveActions('Performance Team')).toBe(true);
    expect(canAccessCorrectiveActions('Viewer')).toBe(false);
  });

  it('keeps Settings content Admin-only (General Manager gets the soft-lock)', () => {
    expect(canAccessSettingsContent('Admin')).toBe(true);
    expect(canAccessSettingsContent('General Manager')).toBe(false);
    expect(canAccessSettings('General Manager')).toBe(false);
    expect(canAccessSettings('Manager')).toBe(false);
  });

  it('allows Team Management for Admin and General Manager', () => {
    expect(canAccessTeamManagement('Admin')).toBe(true);
    expect(canAccessTeamManagement('General Manager')).toBe(true);
    expect(canAccessTeamManagement('Performance Team')).toBe(true);
    expect(canAccessTeamManagement('Manager')).toBe(false);
    expect(canAccessTeamManagement('Executive')).toBe(false);
  });

  it('checks routes with a plain role allow-list', () => {
    expect(canAccessRoute({ role: 'General Manager', allowedRoles: ['Admin', 'General Manager'] })).toBe(true);
    expect(canAccessRoute({ role: 'General Manager', allowedRoles: ['Admin'] })).toBe(false);
    expect(canAccessRoute({ role: 'Manager', allowedRoles: ['Admin', 'General Manager'] })).toBe(false);
    expect(canAccessRoute({ role: undefined, allowedRoles: ['Admin'] })).toBe(false);
  });

  it('shows the stored role as the display label', () => {
    expect(getRoleDisplayLabel('General Manager')).toBe('General Manager');
    expect(getRoleDisplayLabel('Manager')).toBe('Manager');
    expect(getRoleDisplayLabel(undefined)).toBe('');
  });

  it('treats Admin, General Manager and has_unrestricted_team_access as all-teams scope', () => {
    expect(hasAllTeamsScope('Admin')).toBe(true);
    expect(hasAllTeamsScope('General Manager')).toBe(true);
    expect(hasAllTeamsScope('Performance Team')).toBe(true);
    expect(hasAllTeamsScope('Manager', { has_unrestricted_team_access: true })).toBe(true);
    expect(hasAllTeamsScope('Manager', { has_unrestricted_team_access: false })).toBe(false);
    expect(hasAllTeamsScope('Executive', null)).toBe(false);
  });

  it('prefers has_unrestricted_team_access and falls back to legacy is_general_manager', () => {
    expect(readHasUnrestrictedTeamAccess({ has_unrestricted_team_access: true })).toBe(true);
    expect(readHasUnrestrictedTeamAccess({ has_unrestricted_team_access: false, is_general_manager: true })).toBe(false);
    expect(readHasUnrestrictedTeamAccess({ is_general_manager: true })).toBe(true);
    expect(readHasUnrestrictedTeamAccess({ is_general_manager: false })).toBe(false);
    expect(readHasUnrestrictedTeamAccess(null)).toBe(false);
    expect(hasAllTeamsScope('Manager', { is_general_manager: true })).toBe(true);
  });
});
