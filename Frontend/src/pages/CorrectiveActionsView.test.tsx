import { MemoryRouter } from 'react-router-dom';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PMSAction } from '../types';

const { getAllActions, downloadCorrectiveActionsPowerPoint } = vi.hoisted(() => ({
  getAllActions: vi.fn(),
  downloadCorrectiveActionsPowerPoint: vi.fn(() => Promise.resolve()),
}));

vi.mock('../hooks/useActionStore', () => ({
  useActionStore: () => ({ getAllActions }),
}));

vi.mock('../utils/correctiveActionPowerPoint', () => ({
  downloadCorrectiveActionsPowerPoint,
}));

import CorrectiveActionsView from './CorrectiveActionsView';

const actions: PMSAction[] = [
  {
    id: 'a1', employee_id: 'EMP-1', employee_name: 'Agent One', team: 'Inbound', month: 'June',
    action_type: 'Coaching', action_text: 'Review call handling', root_cause_note: 'AHT gap',
    created_by: 'Admin', created_at: '2026-06-15T10:00:00Z', synced: true,
  },
  {
    id: 'a2', employee_id: 'EMP-2', employee_name: 'Agent Two', team: 'Outbound', month: 'May',
    action_type: 'PIP', action_text: 'Improve productivity', root_cause_note: '',
    created_by: 'Executive', created_at: '2026-05-15T10:00:00Z', synced: false,
  },
];

describe('CorrectiveActionsView', () => {
  beforeEach(() => {
    getAllActions.mockReset();
    getAllActions.mockReturnValue(actions);
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:actions') });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
  });

  it('renders action records and summary metrics from the action store', () => {
    render(<MemoryRouter><CorrectiveActionsView /></MemoryRouter>);

    expect(screen.getByRole('heading', { name: 'Corrective Actions' })).toBeInTheDocument();
    expect(screen.getByText('Agent One')).toBeInTheDocument();
    expect(screen.getByText('Agent Two')).toBeInTheDocument();
    expect(screen.getByText('Visible actions').parentElement).toHaveTextContent('2');
    expect(screen.getByText('Pending sync').parentElement).toHaveTextContent('1');
  });

  it('filters records before exporting a PowerPoint document', async () => {
    render(<MemoryRouter><CorrectiveActionsView /></MemoryRouter>);

    fireEvent.change(screen.getByLabelText('Filter by team'), { target: { value: 'Inbound' } });
    expect(screen.getByText('Agent One')).toBeInTheDocument();
    expect(screen.queryByText('Agent Two')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Export PowerPoint' }));
    await waitFor(() => expect(downloadCorrectiveActionsPowerPoint).toHaveBeenCalledWith(
      [actions[0]],
      { team: 'Inbound', month: 'All months', type: 'All types' },
    ));
  });
});
