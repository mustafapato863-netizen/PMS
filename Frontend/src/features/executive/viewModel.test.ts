import { describe, expect, it } from 'vitest';
import type { ExecutivePerson, ExecutivePeriod } from './types';
import { executivePersonPath } from './viewModel';

const period = { key: '2026-06', year: 2026, month: 'June' } as ExecutivePeriod;

describe('executivePersonPath (people rows)', () => {
  it('opens a corporate person on their canonical team scorecard, keeping the period and branch', () => {
    const person = { employee_id: 'E1', name: 'Analyst', team: 'Pre-Approvals OP Dubai', performance_level: 'Corporate' } as unknown as ExecutivePerson;
    expect(executivePersonPath(person, period, 'Dubai'))
      .toBe('/team/pre-approvals-op-final?performance_level=Corporate&month=June&year=2026&employee_ids=E1&branch=dubai');
  });

  it('opens an employee on their profile, not a team page', () => {
    const person = { employee_id: 'E1', name: 'Analyst', team: 'Pre-Approvals IP Offshore', performance_level: 'Employee' } as unknown as ExecutivePerson;
    expect(executivePersonPath(person, period, 'Dubai')).toMatch(/^\/employee\/E1\?/);
  });
});
