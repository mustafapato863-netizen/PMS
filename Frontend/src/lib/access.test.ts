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
} from './access';

describe('access helpers (Option A: stored "General Manager" role)', () => {
  it('uses the Backend role string', () => {
    expect(ROLE_GENERAL_MANAGER).toBe('General Manager');
    expect(USER_ROLE_OPTIONS).toContain('General Manager');
  });

  it('identifies Admin and General Manager by role string only', () => {
    expect(isAdminRole('Admin')).toBe(true);
    expect(isAdminRole('General Manager')).toBe(false);
    expect(isGeneralManagerRole('General Manager')).toBe(true);
    expect(isGeneralManagerRole('Manager')).toBe(false);
    expect(isGeneralManagerRole(null)).toBe(false);
  });

  it('opens broad product pages to Admin and General Manager only', () => {
    expect(canAccessBroadAppPages('Admin')).toBe(true);
    expect(canAccessBroadAppPages('General Manager')).toBe(true);
    for (const role of ['Manager', 'Executive', 'Viewer', 'Agent', undefined]) {
      expect(canAccessBroadAppPages(role)).toBe(false);
    }
  });

  it('opens Corrective Actions to Admin, Executive and General Manager', () => {
    expect(canAccessCorrectiveActions('Admin')).toBe(true);
    expect(canAccessCorrectiveActions('Executive')).toBe(true);
    expect(canAccessCorrectiveActions('General Manager')).toBe(true);
    expect(canAccessCorrectiveActions('Manager')).toBe(false);
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

  it('treats Admin, General Manager and the legacy all-teams flag as all-teams scope', () => {
    expect(hasAllTeamsScope('Admin')).toBe(true);
    expect(hasAllTeamsScope('General Manager')).toBe(true);
    expect(hasAllTeamsScope('Manager', { is_general_manager: true })).toBe(true);
    expect(hasAllTeamsScope('Manager', { is_general_manager: false })).toBe(false);
    expect(hasAllTeamsScope('Executive', null)).toBe(false);
  });
});
