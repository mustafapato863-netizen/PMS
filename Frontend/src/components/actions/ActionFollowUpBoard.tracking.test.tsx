import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import type { PMSAction } from '../../types';
import { ActionFollowUpBoard, EMPTY_FOLLOW_UP_SUMMARY } from './ActionFollowUpBoard';

const undatedAction: PMSAction = {
  id: 'a1',
  employee_id: 'EMP-1',
  employee_name: 'Agent One',
  team: 'Inbound',
  month: 'September',
  action_type: 'Coaching',
  action_text: 'Review call handling',
  root_cause_note: 'AHT gap',
  created_by: 'Admin',
  created_at: '2026-09-01T00:00:00Z',
  synced: true,
  status: 'Open',
  due_date: null,
  owner: { id: 'owner-1', name: 'Ada Owner' },
};

function renderBoard(onStatusChange = vi.fn()) {
  return render(
    <MemoryRouter>
      <ActionFollowUpBoard
        actions={[undatedAction]}
        summary={{ ...EMPTY_FOLLOW_UP_SUMMARY, open: 1 }}
        canEdit
        owners={[{ id: 'owner-1', name: 'Ada Owner' }]}
        teams={['Inbound']}
        months={['September']}
        filters={{}}
        onFiltersChange={vi.fn()}
        onStatusChange={onStatusChange}
      />
    </MemoryRouter>,
  );
}

describe('ActionFollowUpBoard inline edits', () => {
  it('sets a missing due date and sends the status with the date only', async () => {
    const user = userEvent.setup();
    const onStatusChange = vi.fn();
    renderBoard(onStatusChange);

    // The board renders each action twice (table and card layouts); both forms share the same handler.
    const due = new Date();
    due.setDate(due.getDate() + 7);
    const dueDate = due.toISOString().slice(0, 10);
    fireEvent.change(screen.getAllByLabelText('Set due date for Review call handling')[0], { target: { value: dueDate } });
    await user.click(screen.getAllByRole('button', { name: 'Save' })[0]);

    expect(onStatusChange).toHaveBeenCalledTimes(1);
    expect(onStatusChange).toHaveBeenCalledWith('a1', { status: 'Open', due_date: dueDate });
    const update = onStatusChange.mock.calls[0][1] as Record<string, unknown>;
    expect(update).not.toHaveProperty('owner_user_id');
  });

  it('sends a status change alone, without the owner or the due date', async () => {
    const user = userEvent.setup();
    const onStatusChange = vi.fn();
    renderBoard(onStatusChange);

    await user.selectOptions(screen.getAllByLabelText('Status for Review call handling')[0], 'In Progress');

    expect(onStatusChange).toHaveBeenCalledWith('a1', { status: 'In Progress' });
    const update = onStatusChange.mock.calls[0][1] as Record<string, unknown>;
    expect(update).not.toHaveProperty('due_date');
    expect(update).not.toHaveProperty('owner_user_id');
  });
});
