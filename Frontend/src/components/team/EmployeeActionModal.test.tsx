import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TeamAgentRow } from '../../hooks/usePerformanceData';
import EmployeeActionModal from './EmployeeActionModal';

vi.mock('../../hooks/useActionStore', () => ({
  useActionStore: () => ({
    saveAction: vi.fn(),
    updateAction: vi.fn(),
    isSaving: false,
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
});
