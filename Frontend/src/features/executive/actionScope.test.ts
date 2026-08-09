import { describe, expect, it } from 'vitest';
import type { AgentRecord, PMSAction } from '../../types';
import { filterActionsByPerformanceScope } from './actionScope';

const agent = (employeeId: string, team: string, region: string) => ({
  identity: { employee_id: employeeId, name: employeeId, month: 'May', team },
  region,
}) as AgentRecord;

const action = (id: string, employeeId: string, team: string) => ({
  id,
  employee_id: employeeId,
  employee_name: employeeId,
  team,
  month: 'May',
  action_type: 'Coaching',
  action_text: 'Follow up',
  root_cause_note: 'Quality',
  created_by: 'Admin',
  created_at: '2026-05-31T00:00:00Z',
  synced: true,
}) as PMSAction;

describe('filterActionsByPerformanceScope', () => {
  it('removes actions for employees outside the selected region scope', () => {
    const actions = [
      action('uae-action', 'UAE-1', 'Coding'),
      action('egy-action', 'EGY-1', 'Outbound'),
    ];
    const uaeAgents = [agent('UAE-1', 'Coding', 'UAE')];

    expect(filterActionsByPerformanceScope(actions, uaeAgents).map((item) => item.id))
      .toEqual(['uae-action']);
  });

  it('matches employee identifiers without case sensitivity', () => {
    expect(filterActionsByPerformanceScope(
      [action('matched', 'sghd001', 'Sales')],
      [agent('SGHD001', 'Sales', 'UAE')],
    )).toHaveLength(1);
  });
});
