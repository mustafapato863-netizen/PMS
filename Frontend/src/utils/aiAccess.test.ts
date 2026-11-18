import { describe, it, expect } from 'vitest';
import { hasAiAccess, personaLabel, DEFAULT_AI_TIER } from './aiAccess';

describe('hasAiAccess', () => {
  it('defaults to admin_only tier', () => {
    expect(DEFAULT_AI_TIER).toBe('admin_only');
    expect(hasAiAccess('Admin')).toBe(true);
    expect(hasAiAccess('Manager')).toBe(false);
    expect(hasAiAccess('Agent')).toBe(false);
  });

  it('admin_only allows only Admin', () => {
    expect(hasAiAccess('Admin', 'admin_only')).toBe(true);
    expect(hasAiAccess('General Manager', 'admin_only')).toBe(false);
    expect(hasAiAccess('Manager', 'admin_only')).toBe(false);
  });

  it('managers_and_admins allows Admin, GM, Manager, Executive', () => {
    for (const role of ['Admin', 'General Manager', 'Manager', 'Executive']) {
      expect(hasAiAccess(role, 'managers_and_admins')).toBe(true);
    }
    expect(hasAiAccess('Agent', 'managers_and_admins')).toBe(false);
    expect(hasAiAccess('Employee', 'managers_and_admins')).toBe(false);
  });

  it('all_authenticated_users allows any role with a session', () => {
    for (const role of ['Admin', 'Manager', 'Employee', 'Agent', 'Viewer']) {
      expect(hasAiAccess(role, 'all_authenticated_users')).toBe(true);
    }
    expect(hasAiAccess(null, 'all_authenticated_users')).toBe(false);
  });
});

describe('personaLabel', () => {
  it('maps roles to display labels', () => {
    expect(personaLabel('Admin')).toBe('Global');
    expect(personaLabel('Manager')).toBe('Manager');
    expect(personaLabel('Agent', true)).toBe('My 360°');
    expect(personaLabel('Employee')).toBe('My 360°');
  });
});
