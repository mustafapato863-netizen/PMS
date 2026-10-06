import { describe, expect, it } from 'vitest';
import {
  ROLE_FUNCTION_VIEWER,
  ROUTE_ROLES,
  canAccessCorrectiveActions,
  canAccessFunctionSummary,
  canAccessInsights,
  canAccessPlanning,
  canAccessRoute,
  canSeeReportsNav,
  executiveViewForRole,
  isCorporateReadOnly,
  readAccessibleFunctions,
} from './access';

describe('Executive v1 access (Mustafa / CoS defaults)', () => {
  it('centralises the Function Viewer role string', () => {
    expect(ROLE_FUNCTION_VIEWER).toBe('Function Viewer');
  });

  it('picks the Executive view by role', () => {
    expect(executiveViewForRole('Admin')).toBe('corporate');
    expect(executiveViewForRole('General Manager')).toBe('corporate');
    expect(executiveViewForRole('Executive')).toBe('corporate');
    expect(executiveViewForRole('Viewer')).toBe('corporate');
    expect(executiveViewForRole('Manager')).toBe('managerial');
    expect(executiveViewForRole('Function Viewer')).toBe('function');
  });

  it('keeps Corporate read-only for Executive and Viewer', () => {
    expect(isCorporateReadOnly('Executive')).toBe(true);
    expect(isCorporateReadOnly('Viewer')).toBe(true);
    expect(isCorporateReadOnly('Admin')).toBe(false);
    expect(isCorporateReadOnly('General Manager')).toBe(false);
  });

  it('gives Manager Reports, Planning and Corrective Actions but never Insights', () => {
    expect(canSeeReportsNav('Manager')).toBe(true);
    expect(canAccessPlanning('Manager')).toBe(true);
    expect(canAccessCorrectiveActions('Manager')).toBe(true);
    expect(canAccessInsights('Manager')).toBe(false);
  });

  it('gives Function Viewer the Reports library but no Insights, Planning or Corrective Actions', () => {
    expect(canSeeReportsNav('Function Viewer')).toBe(true);
    expect(canAccessInsights('Function Viewer')).toBe(false);
    expect(canAccessPlanning('Function Viewer')).toBe(false);
    expect(canAccessCorrectiveActions('Function Viewer')).toBe(false);
  });

  it('opens Function Summary to Admin, General Manager and Function Viewer only', () => {
    for (const role of ['Admin', 'General Manager', 'Function Viewer']) expect(canAccessFunctionSummary(role)).toBe(true);
    for (const role of ['Manager', 'Executive', 'Viewer', 'Agent']) expect(canAccessFunctionSummary(role)).toBe(false);
  });

  it('route guard lists match the helpers', () => {
    const roles = ['Admin', 'General Manager', 'Manager', 'Executive', 'Viewer', 'Agent', 'Function Viewer'];
    for (const role of roles) {
      expect(canAccessRoute({ role, allowedRoles: ROUTE_ROLES.insights })).toBe(canAccessInsights(role));
      expect(canAccessRoute({ role, allowedRoles: ROUTE_ROLES.planning })).toBe(canAccessPlanning(role));
      expect(canAccessRoute({ role, allowedRoles: ROUTE_ROLES.correctiveActions })).toBe(canAccessCorrectiveActions(role));
      expect(canAccessRoute({ role, allowedRoles: ROUTE_ROLES.functionSummary })).toBe(canAccessFunctionSummary(role));
    }
  });

  it('reads accessible_functions from /auth/me when present', () => {
    expect(readAccessibleFunctions({ accessible_functions: ['RCM', ' Marketing '] } as never)).toEqual(['RCM', 'Marketing']);
    expect(readAccessibleFunctions({} as never)).toEqual([]);
    expect(readAccessibleFunctions(null as never)).toEqual([]);
  });
});
