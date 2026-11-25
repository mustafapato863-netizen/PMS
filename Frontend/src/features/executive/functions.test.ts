import { describe, expect, it } from 'vitest';
import { allowedFunctionsFor, executiveFunctionForTeam, functionFromSlug, functionSlug, isTeamInFunctions } from './functions';
import { teamPath } from '../../types';
import { FIXTURE_TEAM_FUNCTIONS } from './executive.fixture';

describe('allowedFunctionsFor', () => {
  it('gives global roles all current functions regardless of accessible_functions', () => {
    expect(allowedFunctionsFor('Admin', ['RCM'])).toEqual([
      'Call Center', 'RCM', 'Marketing', 'Sales', 'CSR', 'Pharmacy',
      'Finance', 'Human Resources', 'IT', 'Administration', 'Quality Management',
      'ER Dr', 'Radiology',
    ]);
    expect(allowedFunctionsFor('General Manager')).toHaveLength(13);
  });

  it('limits a Function Viewer to accessible_functions, case-insensitively, in display order', () => {
    expect(allowedFunctionsFor('Function Viewer', ['pre-approvals', ' RCM '])).toEqual(['RCM', 'Pre-Approvals']);
  });

  it('drops unknown names and fails closed when no function is assigned', () => {
    expect(allowedFunctionsFor('Function Viewer', ['Treasury Desk'])).toEqual([]);
    expect(allowedFunctionsFor('Function Viewer', ['Finance'])).toEqual(['Finance']);
    expect(allowedFunctionsFor('Function Viewer', [])).toEqual([]);
    expect(allowedFunctionsFor('Function Viewer')).toEqual([]);
  });

  it.each(['Sales', 'CSR', 'Pharmacy', 'ER Dr', 'Radiology'] as const)('keeps %s grants isolated and round-trips their summary route', (name) => {
    expect(allowedFunctionsFor('Function Director', [name])).toEqual([name]);
    expect(isTeamInFunctions(name, [name])).toBe(true);
    expect(isTeamInFunctions('Coding', [name])).toBe(false);
    expect(isTeamInFunctions('Inbound', [name])).toBe(false);
    expect(functionFromSlug(functionSlug(name))).toBe(name);
  });
});

describe('function slugs and team paths', () => {
  it('round-trips slugs and rejects unknown ones', () => {
    expect(functionSlug('Pre-Approvals')).toBe('pre-approvals');
    expect(functionFromSlug('call-center')).toBe('Call Center');
    expect(functionFromSlug('finance')).toBe('Finance');
    expect(functionFromSlug('human-resources')).toBe('Human Resources');
    expect(functionFromSlug('it')).toBe('IT');
    expect(functionFromSlug('administration')).toBe('Administration');
    expect(functionFromSlug('quality-management')).toBe('Quality Management');
    expect(functionSlug('ER Dr')).toBe('er-dr');
    expect(functionFromSlug('er-dr')).toBe('ER Dr');
    expect(functionFromSlug('radiology')).toBe('Radiology');
    expect(functionFromSlug('quality-case-management')).toBe('RCM');
    expect(functionFromSlug('treasury')).toBeNull();
  });

  it('uses the canonical route id for known teams and a slug only for unknown ones', () => {
    expect(teamPath('Pre-Approvals IP Offshore')).toBe('/team/pre-approvals');
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

  it('preserves the narrow legacy grant without upgrading it to RCM', () => {
    expect(allowedFunctionsFor('Function Director', ['Pre-Approvals'])).toEqual(['Pre-Approvals']);
    expect(isTeamInFunctions('Pre-Approvals OP Final', ['Pre-Approvals'])).toBe(true);
    expect(isTeamInFunctions('Coding', ['Pre-Approvals'])).toBe(false);
    expect(isTeamInFunctions('Pre-Approvals IP Offshore', ['Pre-Approvals'], FIXTURE_TEAM_FUNCTIONS)).toBe(false);
  });
});

describe('executiveFunctionForTeam (clinical functions)', () => {
  it('maps the new UAE clinical teams to their own functions', () => {
    expect(executiveFunctionForTeam('ER Dr')).toBe('ER Dr');
    expect(executiveFunctionForTeam('Radiologist')).toBe('Radiology');
    expect(executiveFunctionForTeam('Radiology')).toBe('Radiology');
    expect(executiveFunctionForTeam('Qlty&Case-Mngt')).toBe('RCM');
    expect(executiveFunctionForTeam('Quality and Case Management')).toBe('RCM');
  });

  it('leaves Quality Management mapped to itself', () => {
    expect(executiveFunctionForTeam('Quality Management')).toBe('Quality Management');
  });
});
