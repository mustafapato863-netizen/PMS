import { describe, expect, it } from 'vitest';
import { summarizeActions, type FollowUpAction } from './compose';
import type { ExecutivePeriod } from './types';

const today = new Date(2026, 9, 14);
const effective = { key: '2026-10', year: 2026, month: 'October' } as ExecutivePeriod;

const action = (overrides: Partial<FollowUpAction> & { id: string }): FollowUpAction => ({
  employee_name: 'Agent',
  team: 'Inbound',
  status: 'Open',
  action_type: 'Coaching',
  action_text: 'Coach on hold time',
  created_at: '2026-10-01T08:00:00Z',
  ...overrides,
});

const actions: FollowUpAction[] = [
  action({ id: 'C', created_at: '2026-10-05T08:00:00Z' }),
  action({ id: 'A', due_date: '2026-10-10', created_at: '2026-09-01T08:00:00Z' }),
  action({ id: 'B', due_date: '2026-10-16', created_at: '2026-10-01T08:00:00Z' }),
  action({ id: 'D', created_at: '2026-10-09T08:00:00Z' }),
  action({ id: 'E', due_date: '2026-11-20', created_at: '2026-10-02T08:00:00Z' }),
  action({ id: 'F', status: 'Completed', completed_at: '2026-10-03T09:00:00Z', created_at: '2026-09-20T08:00:00Z' }),
  action({ id: 'G', status: 'Completed', completed_at: '2026-09-28T09:00:00Z', created_at: '2026-09-10T08:00:00Z' }),
];

describe('corrective action rows for the card', () => {
  const summary = summarizeActions(actions, today, effective);

  it('lists overdue first, then due this week, then dated open actions, then undated, newest first in each group, then closed this period', () => {
    expect(summary.rows?.map((row) => row.id)).toEqual(['A', 'B', 'E', 'D', 'C', 'F']);
  });

  it('leaves out completed actions from earlier periods', () => {
    expect(summary.rows?.map((row) => row.id)).not.toContain('G');
  });

  it('keeps the four-row preview and the tile counts unchanged', () => {
    expect(summary.actions).toHaveLength(4);
    expect(summary.summary).toEqual({
      as_of: '2026-10-14',
      open: 5,
      overdue: 1,
      due_this_week: 1,
      closed_in_month: 1,
    });
  });

  it('carries the action text, type, reason and KPI into each row', () => {
    const [first] = summary.rows ?? [];
    expect(first).toMatchObject({ id: 'A', action_type: 'Coaching', action_text: 'Coach on hold time', follow_up_state: 'overdue' });
  });
});
