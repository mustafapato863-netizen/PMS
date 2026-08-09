import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import ReportsView from './ReportsView';

const mocks = vi.hoisted(() => ({
  canExport: true,
  refetch: vi.fn(),
  deleteReport: vi.fn(),
  generatedReports: [] as Array<Record<string, unknown>>,
}));

vi.mock('../context/RoleContext', () => ({
  useUserRole: () => ({ role: mocks.canExport ? 'Admin' : 'Viewer', fetchWithRole: vi.fn() }),
}));

vi.mock('../components/reports/ReportConfigModal', () => ({
  default: ({ template, initialConfiguration }: { template: { name: string }; initialConfiguration: { team?: string | null } }) => (
    <div data-testid="report-modal">{template.name}|{initialConfiguration.team || 'all'}</div>
  ),
}));

vi.mock('../hooks/api/useReports', () => ({
  useReportTemplates: () => ({
    data: [
      { type: 'executive', category: 'executive', name: 'Executive Performance Report', description: 'Summary', formats: ['pptx', 'pdf'], sections: ['summary', 'details'] },
      { type: 'team', category: 'team', name: 'Team Performance Report', description: 'Team detail', formats: ['pptx', 'pdf'], sections: ['summary', 'details'] },
    ],
    isLoading: false,
    error: null,
  }),
  useReportOptions: () => ({
    data: {
      periods: [{ year: 2026, month: 'June', key: '2026-06' }],
      teams: ['Marketing'],
      regions: ['EGY'],
      performance_levels: ['Managerial'],
      positions: ['Manager'],
      employees: [],
      grades: ['A'],
      statuses: ['Meets'],
      can_export: mocks.canExport,
    },
    isLoading: false,
    error: null,
  }),
  useGeneratedReports: () => ({ data: { items: mocks.generatedReports, total: mocks.generatedReports.length, page: 1, page_size: 10 }, isLoading: false, isFetching: false, refetch: mocks.refetch }),
  useDeleteGeneratedReport: () => ({ mutateAsync: mocks.deleteReport, isPending: false, error: null }),
  useSavedReportTemplates: () => ({ data: [], isLoading: false }),
}));

describe('ReportsView', () => {
  const renderView = () => render(<MemoryRouter><ReportsView /></MemoryRouter>);
  beforeEach(() => {
    mocks.canExport = true;
    mocks.refetch.mockReset();
    mocks.deleteReport.mockReset();
    mocks.deleteReport.mockResolvedValue({ id: 'report-1', name: 'June Team Report' });
    mocks.generatedReports = [];
  });

  it('renders backend templates and the authorized reporting period', () => {
    renderView();

    expect(screen.getByRole('heading', { name: 'Report Builder' })).toBeInTheDocument();
    expect(screen.getByText('Executive Performance Report')).toBeInTheDocument();
    expect(screen.getByText('Team Performance Report')).toBeInTheDocument();
    expect(screen.getAllByText('PPTX').length).toBeGreaterThan(0);
    expect(screen.getAllByText('PDF').length).toBeGreaterThan(0);
    expect(screen.getByRole('combobox', { name: 'Select Reporting Period' })).toHaveValue('2026-06');
    expect(screen.getAllByRole('button', { name: /Generate report/i })).toHaveLength(2);
  });

  it('shows preview-only state when the authenticated role cannot export', () => {
    mocks.canExport = false;
    renderView();

    expect(screen.getByText(/Preview only —/)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Preview only' })).toHaveLength(2);
    screen.getAllByRole('button', { name: 'Preview only' }).forEach((button) => expect(button).toBeDisabled());
  });

  it('shows an explicit empty state for generated reports', () => {
    renderView();

    expect(screen.getByText('No generated reports yet.')).toBeInTheDocument();
  });

  it('confirms and deletes a generated report', async () => {
    const user = userEvent.setup();
    mocks.generatedReports = [{
      id: 'report-1',
      name: 'June Team Report',
      report_type: 'team',
      period: 'June 2026',
      created_at: '2026-07-22T16:09:00Z',
      format: 'pptx',
      file_name: 'June_Team_Report.pptx',
      download_url: '/api/reports/report-1/download',
    }];
    renderView();

    await user.click(screen.getByRole('button', { name: 'Delete June Team Report' }));
    expect(screen.getByRole('alertdialog', { name: 'Delete this report?' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Delete report' }));

    await waitFor(() => expect(mocks.deleteReport).toHaveBeenCalledWith('report-1'));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(screen.getByText('June Team Report deleted successfully.')).toBeInTheDocument();
  });
});
