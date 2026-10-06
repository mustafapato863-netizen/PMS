import { describe, expect, it } from 'vitest';
import { allowedFunctionsFor, functionFromSlug, functionSlug, isTeamInFunctions, teamPath } from './functions';
import { FIXTURE_TEAM_FUNCTIONS } from './executive.fixture';

describe('allowedFunctionsFor', () => {
  it('gives Admin and General Manager all four functions regardless of accessible_functions', () => {
    expect(allowedFunctionsFor('Admin', ['RCM'])).toEqual(['Call Center', 'RCM', 'Pre-Approvals', 'Marketing']);
    expect(allowedFunctionsFor('General Manager')).toHaveLength(4);
  });

  it('limits a Function Viewer to accessible_functions, case-insensitively, in display order', () => {
    expect(allowedFunctionsFor('Function Viewer', ['pre-approvals', ' RCM '])).toEqual(['RCM', 'Pre-Approvals']);
  });

  it('drops unknown names and fails closed when no function is assigned', () => {
    expect(allowedFunctionsFor('Function Viewer', ['Finance'])).toEqual([]);
    expect(allowedFunctionsFor('Function Viewer', [])).toEqual([]);
    expect(allowedFunctionsFor('Function Viewer')).toEqual([]);
  });
});

describe('function slugs and team paths', () => {
  it('round-trips slugs and rejects unknown ones', () => {
    expect(functionSlug('Pre-Approvals')).toBe('pre-approvals');
    expect(functionFromSlug('call-center')).toBe('Call Center');
    expect(functionFromSlug('finance')).toBeNull();
  });

  it('uses the sidebar slug rule for team dashboards', () => {
    expect(teamPath('Pre-Approvals IP Offshore')).toBe('/team/pre-approvals-ip-offshore');
    expect(teamPath('R&D Team')).toBe('/team/randd-team');
  });
});

describe('isTeamInFunctions (Function Viewer page scope)', () => {
  it('follows the disjoint card membership (IP Offshore → RCM, CSR outside the four)', () => {
    expect(isTeamInFunctions('Pre-Approvals IP Offshore', ['RCM'], FIXTURE_TEAM_FUNCTIONS)).toBe(true);
    expect(isTeamInFunctions('Inbound', ['RCM'], FIXTURE_TEAM_FUNCTIONS)).toBe(false);
    expect(isTeamInFunctions('CSR', ['Call Center', 'RCM', 'Pre-Approvals', 'Marketing'], FIXTURE_TEAM_FUNCTIONS)).toBe(false);
  });

  it('also allows a backend team_functions overlap (UAE pre-approvals listed under RCM)', () => {
    expect(isTeamInFunctions('Pre-Approvals OP Final', ['RCM'], FIXTURE_TEAM_FUNCTIONS)).toBe(true);
    expect(isTeamInFunctions(null, ['RCM'])).toBe(false);
  });
});
