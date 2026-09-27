import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { TeamAgentRow } from '../../hooks/usePerformanceData';
import EmployeeActionModal from './EmployeeActionModal';

const { saveAction } = vi.hoisted(() => ({
  saveAction: vi.fn(async () => ({ success: true, synced: true, message: 'Action saved successfully.' })),
}));

vi.mock('../../hooks/useActionStore', () => ({
  useActionStore: () => ({
    saveAction,
    updateAction: vi.fn(),
    isSaving: false,
  }),
}));

vi.mock('../../lib/apiClient', () => ({
  apiFetch: vi.fn(async (url: string) => {
    if (String(url).includes('/owners')) return { success: true, data: [{ id: 'owner-1', name: 'Ada Owner' }] };
    if (String(url).includes('/planning')) return { success: true, data: [{ id: 'plan-1', name: 'Inbound recovery', team: 'Inbound', status: 'In Progress' }] };
    return { success: true, data: [] };
  }),
}));

vi.mock('../../context/auth', () => ({
  useAuth: () => ({ currentUser: { name: 'Test Admin', role: 'Admin' } }),
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

describe('EmployeeActionModal', () => {
  it('renders above the application shell with a visible fixed header and scrollable body', () => {
    const { container } = render(
      <EmployeeActionModal employee={employee} month="June" onClose={vi.fn()} />,
    );

    const dialog = screen.getByRole('dialog', { name: 'Test Agent' });
    expect(container).not.toContainElement(dialog);
    expect(dialog.closest('.fixed')?.parentElement).toBe(document.body);
    expect(dialog).toHaveClass('flex', 'flex-col', 'overflow-hidden', 'sm:max-h-[94vh]');
    expect(screen.getByRole('heading', { name: 'Test Agent' }).parentElement?.parentElement).toHaveClass('shrink-0');
    expect(dialog.querySelector('form')).toHaveClass('min-h-0', 'flex-1', 'overflow-y-auto');
  });

  it('reveals tracking fields and requires a due date before saving', async () => {
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <EmployeeActionModal employee={employee} month="June" onClose={vi.fn()} />
      </QueryClientProvider>,
    );

    await user.click(screen.getByRole('checkbox', { name: 'Track as action plan' }));
    expect(screen.getByLabelText('Owner')).toBeInTheDocument();
    expect(screen.getByLabelText('Due date')).toBeInTheDocument();
    expect(screen.getByLabelText('Priority')).toBeInTheDocument();
    expect(screen.getByLabelText('Linked KPI')).toBeInTheDocument();
    expect(await screen.findByRole('option', { name: 'Ada Owner' })).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText('Describe the Coaching action in detail...'), 'Coach the booking script');
    await user.click(screen.getByRole('button', { name: 'Save Action' }));
    expect(screen.getByText('A due date is required to track this action.')).toBeInTheDocument();
    expect(saveAction).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText('Due date'), { target: { value: '2026-10-01' } });
    await user.selectOptions(screen.getByLabelText('Owner'), 'owner-1');
    await user.selectOptions(screen.getByLabelText('Priority'), 'High');
    await user.click(screen.getByRole('button', { name: 'Save Action' }));
    expect(saveAction).toHaveBeenCalledWith(expect.objectContaining({
      due_date: '2026-10-01',
      owner_user_id: 'owner-1',
      priority: 'High',
      action_text: 'Coach the booking script',
    }));
  });
});
