import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import type { PMSAction } from '../../types';
import { canEditActionFollowUp } from './dueBadge';
import { ActionFollowUpBoard, EMPTY_FOLLOW_UP_SUMMARY } from './ActionFollowUpBoard';

const overdueAction: PMSAction = {
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
  due_date: '2026-09-22',
  days_to_due: -5,
  follow_up_state: 'overdue',
  is_overdue: true,
  owner: { id: 'owner-1', name: 'Ada Owner' },
};

function renderBoard(canEdit: boolean, onStatusChange = vi.fn()) {
  return render(
    <MemoryRouter>
      <ActionFollowUpBoard
        actions={[overdueAction]}
        summary={{ ...EMPTY_FOLLOW_UP_SUMMARY, overdue: 1, open: 1 }}
        canEdit={canEdit}
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

describe('ActionFollowUpBoard', () => {
  it('shows how many days an open action is overdue', () => {
    renderBoard(true);
    expect(screen.getAllByText('5 days overdue').length).toBeGreaterThan(0);
  });

  it('asks for a completion note before marking an action completed', async () => {
    const user = userEvent.setup();
    const onStatusChange = vi.fn();
    renderBoard(true, onStatusChange);

    await user.selectOptions(screen.getAllByLabelText('Status for Review call handling')[0], 'Completed');
    expect(onStatusChange).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Save status' }));
    expect(screen.getByRole('alert')).toHaveTextContent('completion note');
    expect(onStatusChange).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText('Note'), 'Script is now in use');
    await user.click(screen.getByRole('button', { name: 'Save status' }));
    expect(onStatusChange).toHaveBeenCalledWith('a1', { status: 'Completed', completion_note: 'Script is now in use' });
  });

  it('is read-only for Executive and Viewer roles', () => {
    expect(canEditActionFollowUp('Executive')).toBe(false);
    expect(canEditActionFollowUp('Viewer')).toBe(false);
    expect(canEditActionFollowUp('Admin')).toBe(true);
    renderBoard(false);
    expect(screen.queryAllByLabelText('Status for Review call handling')).toHaveLength(0);
    expect(screen.getAllByText('Open').length).toBeGreaterThan(0);
  });
});