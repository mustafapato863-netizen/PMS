import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useReportBuilderStore } from '../../../store/reportBuilderStore';
import Step1Scope from './Step1Scope';

vi.mock('../../../hooks/api/useReports', () => ({
  useReportOptions: () => ({
    data: {
      periods: [
        { year: 2026, month: 'June', key: '2026-06' },
        { year: 2026, month: 'May', key: '2026-05' },
      ],
      teams: ['Inbound'], regions: ['EGY'], performance_levels: ['Employee'], positions: ['Agent'],
      employees: [{ id: '1', name: 'Agent', team: 'Inbound', region: 'EGY', position: 'Agent', performance_level: 'Employee' }],
      grades: [], statuses: [], can_export: true,
    },
    isLoading: false,
    error: null,
  }),
}));

describe('Step1Scope', () => {
  beforeEach(() => useReportBuilderStore.getState().reset());

  it('fills the missing report name even when periods were already initialized', async () => {
    useReportBuilderStore.getState().setConfiguration({
      report_name: '', start_month: 'June', start_year: 2026, end_month: 'May', end_year: 2026,
    });
    render(<Step1Scope />);

    await waitFor(() => expect(screen.getByRole('textbox', { name: /Report Name/i })).toHaveValue('June 2026 Monthly Performance Review'));
    expect(screen.getByText(/Scope is fully defined/i)).toBeInTheDocument();
  });

  it('renders an actionable validation message beside the blocked field', () => {
    render(<Step1Scope validationErrors={{ report_name: 'Enter a clear report name to continue.' }} />);
    expect(screen.getByText('Enter a clear report name to continue.')).toBeInTheDocument();
  });
});
