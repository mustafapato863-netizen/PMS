import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { EvaluationPeriodData } from '../evaluationSettings';
import { EvaluationHistory, type EvaluationHistoryProps } from './EvaluationHistory';

const HISTORY: EvaluationPeriodData['history'] = [
  {
    id: 'approved-june', status: 'approved', lines: [], version_number: 2, month_name: 'June',
    created_at: '2026-06-20T08:00:00+00:00', created_by: 'Ruth Creator',
    approved_at: '2026-06-28T09:30:00+00:00', approved_by: 'Amir Approver',
  },
  { id: 'draft-july', status: 'draft', lines: [], version_number: 3, month_name: 'July', created_at: '2026-07-02T10:00:00+00:00', created_by: 'Ruth Creator' },
  { id: 'legacy', status: 'approved', lines: [], version_number: 1, month_name: 'May' },
];

function props(overrides: Partial<EvaluationHistoryProps> = {}): EvaluationHistoryProps {
  return {
    history: HISTORY,
    revisions: [],
    periodLoading: false,
    monthName: 'June',
    busy: false,
    onRequestRollback: vi.fn(),
    ...overrides,
  };
}

describe('EvaluationHistory who and when', () => {
  it('shows who created and who approved each version, with the absolute time as a tooltip', () => {
    render(<EvaluationHistory {...props()} />);
    const created = screen.getAllByText(/^Created .+ by Ruth Creator$/);
    expect(created).toHaveLength(2);
    const approved = screen.getByText(/^Approved .+ by Amir Approver$/);
    expect(approved).toHaveAttribute('title', new Date('2026-06-28T09:30:00+00:00').toLocaleString());
    expect(created[0]).toHaveAttribute('title', new Date('2026-06-20T08:00:00+00:00').toLocaleString());
  });

  it('shows an approval line only for an approved version', () => {
    render(<EvaluationHistory {...props()} />);
    expect(screen.getAllByText(/^Approved /)).toHaveLength(1);
  });

  it('omits a version\'s who-and-when when the server did not send it, and never writes unknown', () => {
    render(<EvaluationHistory {...props()} />);
    const legacy = screen.getByText('Version 1').closest('li') as HTMLElement;
    expect(legacy).not.toHaveTextContent(/Created|Approved/);
    expect(screen.queryByText(/unknown/i)).not.toBeInTheDocument();
  });
});
