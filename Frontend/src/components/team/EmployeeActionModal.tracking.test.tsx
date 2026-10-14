import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { TeamAgentRow } from '../../hooks/usePerformanceData';
import type { EditableCorrectiveAction } from '../../types';
import EmployeeActionModal from './EmployeeActionModal';

const { saveAction, updateAction, auth } = vi.hoisted(() => ({
  saveAction: vi.fn<(input: Record<string, unknown>) => Promise<{ success: boolean; synced: boolean; message: string }>>(async () => ({ success: true, synced: true, message: 'Action saved successfully.' })),
  updateAction: vi.fn(async () => ({ success: true, synced: true, message: 'Action updated successfully.' })),
  auth: { currentUser: { id: 'owner-1', name: 'Hany Mostafa', role: 'Admin' } as { id?: string; name: string; role: string } | null },
}));

vi.mock('../../hooks/useActionStore', () => ({
  useActionStore: () => ({ saveAction, updateAction, isSaving: false }),
}));

vi.mock('../../lib/apiClient', () => ({
  apiFetch: vi.fn(async (url: string) => {
    if (String(url).includes('/owners')) {
      return { success: true, data: [{ id: 'owner-1', name: 'Ada Owner' }, { id: 'owner-2', name: 'Mona Adel' }] };
    }
    return { success: true, data: [] };
  }),
}));

vi.mock('../../context/auth', () => ({
  useAuth: () => ({ currentUser: auth.currentUser }),
}));

const employee: TeamAgentRow = {
  id: 'EMP-1',
  name: 'Test Agent',
  team: 'Inbound',
  month: 'June',
  performanceLevel: 'Employee',
  score: 91.3,
  gradeClass: 'B',
  gradeLabel: 'B',
  status: 'Meet',
  rootCauseAuto: 'Attendance below target',
  rootCauseNote: '',
  correctiveAction: '',
  suggestedAction: 'Coaching',
  ahtMinutes: 3,
  bookingRate: 0.5,
  attendRate: 0.7,
  raw: {
    identity: { name: 'Test Agent', employee_id: 'EMP-1', team: 'Inbound', month: 'June' },
    calls: { inbound: 10, outbound: 0, total_handled: 10, abandoned: 1, aht_raw: '00:03:00' },
    geo: {
      bookings: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
      attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
    },
    actual: { booking_rate: 0.5, attend_rate: 0.7, abandon_rate: 0.1, quality_rate: 0.9 },
    achievement: { booking_ach: 1, attend_ach: 0.9 },
    evaluation: { score: 91.3, grade: 'B' },
  },
};

const futureDate = (days: number) => new Date(Date.now() + days * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);

function renderModal(editAction?: EditableCorrectiveAction) {
  return render(<EmployeeActionModal employee={employee} month="June" onClose={vi.fn()} editAction={editAction} />);
}

/** The payload object of the last updateAction call (updateAction(id, payload, employee, month)). */
function lastUpdatePayload(): Record<string, unknown> {
  const calls = updateAction.mock.calls as unknown as Array<[string, Record<string, unknown>]>;
  return calls[calls.length - 1][1];
}

const existingAction: EditableCorrectiveAction = {
  id: 'act-1',
  action_type: 'Coaching',
  action_text: 'Coach the booking script',
  root_cause_note: '',
  status: 'Open',
  owner_id: 'owner-1',
  due_date: futureDate(10),
  priority: 'High',
  linked_kpi_key: null,
  plan_id: null,
};

beforeEach(() => {
  saveAction.mockClear();
  updateAction.mockClear();
  auth.currentUser = { id: 'owner-1', name: 'Hany Mostafa', role: 'Admin' };
});

describe('EmployeeActionModal: a new action', () => {
  it('is tracked by default and sends the signed-in owner and the due date', async () => {
    const user = userEvent.setup();
    renderModal();

    expect(screen.getByRole('checkbox', { name: 'Track as action plan' })).toBeChecked();
    await waitFor(() => expect(screen.getByLabelText('Owner')).toHaveValue('owner-1'));
    await user.type(screen.getByPlaceholderText('Describe the Coaching action in detail...'), 'Coach the booking script');
    fireEvent.change(screen.getByLabelText('Due date'), { target: { value: futureDate(7) } });
    await user.click(screen.getByRole('button', { name: 'Save Action' }));

    expect(saveAction).toHaveBeenCalledWith(expect.objectContaining({
      owner_user_id: 'owner-1',
      due_date: futureDate(7),
      priority: 'Medium',
    }));
  });

  it('starts Unassigned when the signed-in user is not on the owner list', async () => {
    auth.currentUser = { id: 'viewer-9', name: 'Other Manager', role: 'Manager' };
    const user = userEvent.setup();
    renderModal();

    await waitFor(() => expect(screen.getByRole('option', { name: 'Ada Owner' })).toBeInTheDocument());
    expect(screen.getByLabelText('Owner')).toHaveValue('');
    await user.type(screen.getByPlaceholderText('Describe the Coaching action in detail...'), 'Coach the booking script');
    fireEvent.change(screen.getByLabelText('Due date'), { target: { value: futureDate(7) } });
    await user.click(screen.getByRole('button', { name: 'Save Action' }));

    expect(saveAction).toHaveBeenCalledWith(expect.objectContaining({ owner_user_id: null, due_date: futureDate(7) }));
  });

  it('sends no tracking fields when the user unticks the toggle', async () => {
    const user = userEvent.setup();
    renderModal();

    await user.click(screen.getByRole('checkbox', { name: 'Track as action plan' }));
    await user.type(screen.getByPlaceholderText('Describe the Coaching action in detail...'), 'Coach the booking script');
    await user.click(screen.getByRole('button', { name: 'Save Action' }));

    expect(saveAction).toHaveBeenCalledTimes(1);
    const payload = saveAction.mock.calls[0][0] as Record<string, unknown>;
    expect(payload).not.toHaveProperty('owner_user_id');
    expect(payload).not.toHaveProperty('due_date');
    expect(payload).not.toHaveProperty('priority');
  });
});

describe('EmployeeActionModal: editing an existing action', () => {
  it('keeps the owner, due date, priority and KPI when the user changes only the text', async () => {
    const user = userEvent.setup();
    renderModal(existingAction);

    expect(screen.getByRole('checkbox', { name: 'Track as action plan' })).toBeChecked();
    await waitFor(() => expect(screen.getByLabelText('Owner')).toHaveValue('owner-1'));
    await user.type(screen.getByDisplayValue('Coach the booking script'), ' and the hold time');
    await user.click(screen.getByRole('button', { name: 'Update Action' }));

    const payload = lastUpdatePayload();
    expect(payload).toMatchObject({ action_text: 'Coach the booking script and the hold time' });
    expect(payload).not.toHaveProperty('owner_user_id');
    expect(payload).not.toHaveProperty('due_date');
    expect(payload).not.toHaveProperty('priority');
    expect(payload).not.toHaveProperty('linked_kpi_key');
    expect(payload).not.toHaveProperty('plan_id');
  });

  it('sends an explicit null owner when the user chooses Unassigned, and keeps the due date', async () => {
    const user = userEvent.setup();
    renderModal(existingAction);

    await waitFor(() => expect(screen.getByLabelText('Owner')).toHaveValue('owner-1'));
    await user.selectOptions(screen.getByLabelText('Owner'), '');
    await user.click(screen.getByRole('button', { name: 'Update Action' }));

    const payload = lastUpdatePayload();
    expect(payload).toHaveProperty('owner_user_id', null);
    expect(payload).not.toHaveProperty('due_date');
  });

  it('refuses to clear the due date while an owner is set, and clears both when the owner is cleared first', async () => {
    const user = userEvent.setup();
    renderModal(existingAction);

    await waitFor(() => expect(screen.getByLabelText('Owner')).toHaveValue('owner-1'));
    await user.click(screen.getByRole('button', { name: 'Clear due date' }));
    await user.click(screen.getByRole('button', { name: 'Update Action' }));
    expect(screen.getByText('A due date is required when an owner or priority is set.')).toBeInTheDocument();
    expect(updateAction).not.toHaveBeenCalled();

    await user.selectOptions(screen.getByLabelText('Owner'), '');
    await user.click(screen.getByRole('button', { name: 'Update Action' }));
    const payload = lastUpdatePayload();
    expect(payload).toHaveProperty('owner_user_id', null);
    expect(payload).toHaveProperty('due_date', null);
  });

  it('does not send tracking fields when the user unticks the toggle on an existing action', async () => {
    const user = userEvent.setup();
    renderModal(existingAction);

    await user.click(screen.getByRole('checkbox', { name: 'Track as action plan' }));
    await user.click(screen.getByRole('button', { name: 'Update Action' }));

    const payload = lastUpdatePayload();
    expect(payload).not.toHaveProperty('owner_user_id');
    expect(payload).not.toHaveProperty('due_date');
    expect(payload).not.toHaveProperty('priority');
  });

  it('saves an overdue action without refusing its past due date, which the user did not set', async () => {
    const user = userEvent.setup();
    renderModal({ ...existingAction, due_date: '2026-01-02' });

    await user.type(screen.getByDisplayValue('Coach the booking script'), ' today');
    await user.click(screen.getByRole('button', { name: 'Update Action' }));

    expect(updateAction).toHaveBeenCalledTimes(1);
    expect(lastUpdatePayload()).not.toHaveProperty('due_date');
  });
});
