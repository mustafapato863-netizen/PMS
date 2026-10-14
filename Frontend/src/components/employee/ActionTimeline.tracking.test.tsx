import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { PMSAction } from '../../types';
import ActionTimeline from './ActionTimeline';

vi.mock('../../context/RoleContext', () => ({ useUserRole: () => ({ role: 'Admin' }) }));
vi.mock('../../hooks/useActionStore', () => ({
  useUpdateActionStatus: () => ({ mutateAsync: vi.fn() }),
}));

const action = {
  id: 'act-1',
  employee_id: 'EMP-1',
  employee_name: 'Test Agent',
  team: 'Inbound',
  month: 'June',
  action_type: 'Coaching',
  action_text: 'Coach the booking script',
  root_cause_note: 'Booking below target',
  created_by: 'Hany Mostafa - Admin',
  created_at: '2026-06-02T08:00:00Z',
  synced: true,
  status: 'Open',
  due_date: '2026-12-01',
  owner: { id: 'owner-1', name: 'Ada Owner' },
  priority: 'High',
  linked_kpi_key: 'Booking Rate',
  plan: null,
} as unknown as PMSAction;

describe('ActionTimeline edit', () => {
  it('passes the owner id, due date, priority and KPI of a saved action to the editor', async () => {
    const user = userEvent.setup();
    const onEditAction = vi.fn();
    render(<ActionTimeline activeMonth="June" localActions={[action]} backendActions={[]} onEditAction={onEditAction} />);

    await user.click(screen.getByRole('button', { name: 'Edit Action' }));

    expect(onEditAction).toHaveBeenCalledWith(expect.objectContaining({
      id: 'act-1',
      owner_id: 'owner-1',
      due_date: '2026-12-01',
      priority: 'High',
      linked_kpi_key: 'Booking Rate',
    }));
  });
});
