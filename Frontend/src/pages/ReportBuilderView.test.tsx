import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { useReportBuilderStore } from '../store/reportBuilderStore';
import ReportBuilderView from './ReportBuilderView';

vi.mock('../hooks/api/useReports', () => ({
  useStoryDraft: () => ({ data: null, isLoading: false, error: null }),
  useSaveStoryDraft: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSaveStoryTemplate: () => ({ mutateAsync: vi.fn(), isPending: false }),
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

vi.mock('../components/reports/builder/Step2Template', () => ({ default: () => <div>Template step loaded</div> }));
vi.mock('../components/reports/builder/Step3Builder', () => ({ default: () => <div>Build step loaded</div> }));
vi.mock('../components/reports/builder/Step4Review', () => ({ default: () => <div>Review step loaded</div> }));
vi.mock('../components/reports/builder/Step5Export', () => ({ default: () => <div>Export step loaded</div> }));

describe('ReportBuilderView navigation', () => {
  beforeEach(() => {
    useReportBuilderStore.getState().reset();
    useReportBuilderStore.getState().setConfiguration({
      report_name: '', start_month: 'June', start_year: 2026, end_month: 'May', end_year: 2026,
    });
  });

  it('initializes the missing name and advances to Template when Next is clicked', async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><ReportBuilderView /></MemoryRouter>);

    await waitFor(() => expect(screen.getByRole('textbox', { name: /Report Name/i })).toHaveValue('June 2026 Monthly Performance Review'));
    expect(useReportBuilderStore.getState().configuration).toMatchObject({
      report_name: 'June 2026 Monthly Performance Review', start_month: 'June', start_year: 2026,
      end_month: 'May', end_year: 2026,
    });
    await user.click(screen.getByRole('button', { name: /^Next/i }));
    expect(useReportBuilderStore.getState().currentStep).toBe(2);
    expect(await screen.findByText('Template step loaded')).toBeInTheDocument();
  });

  it('shows the reason and focuses an invalid field instead of failing silently', async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><ReportBuilderView /></MemoryRouter>);
    const name = await screen.findByRole('textbox', { name: /Report Name/i });
    await user.clear(name);
    await user.click(screen.getByRole('button', { name: /^Next/i }));

    expect(screen.getByText('Enter a clear report name to continue.')).toBeInTheDocument();
    await waitFor(() => expect(name).toHaveFocus());
  });
});
