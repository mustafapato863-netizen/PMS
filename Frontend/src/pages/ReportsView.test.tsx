import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import ReportsView from './ReportsView';

const mocks = vi.hoisted(() => ({
  canExport: true,
  refetch: vi.fn(),
  generateReport: vi.fn(),
  deleteReport: vi.fn(),
  deleteReports: vi.fn(),
  generatedReports: [] as Array<Record<string, unknown>>,
}));

vi.mock('../context/RoleContext', () => ({
  useUserRole: () => ({ role: mocks.canExport ? 'Admin' : 'Viewer', fetchWithRole: vi.fn() }),
}));

vi.mock('../hooks/api/useReports', () => ({
  useReportTemplates: () => ({
    data: [
      { type: 'executive', category: 'executive', name: 'Executive Performance Report', description: 'Summary', formats: ['pptx', 'pdf'], sections: ['summary', 'details'] },
      { type: 'team', category: 'team', name: 'Team Performance Report', description: 'Team detail', formats: ['pptx', 'pdf'], sections: ['summary', 'details'] },
      { type: 'team_marketing', category: 'team', name: 'Marketing Summary - PowerPoint', description: 'Marketing detail', formats: ['pptx'], sections: ['summary', 'details'] },
    ],
    isLoading: false,
    error: null,
  }),
  useReportOptions: () => ({
    data: {
      periods: [{ year: 2026, month: 'June', key: '2026-06' }, { year: 2026, month: 'April', key: '2026-04' }],
      teams: ['Marketing'],
      regions: ['EGY'],
      performance_levels: ['Employee', 'Managerial', 'Corporate'],
      positions: ['Analyst'],
      employees: [{ id: 'EMP1', name: 'Alice Smith', team: 'Marketing', position: 'Analyst', performance_level: 'Employee', region: 'EGY' }],
      grades: ['A'],
      statuses: ['Meets'],
      kpis: ['quality'],
      can_export: mocks.canExport,
    },
    isLoading: false,
    error: null,
  }),
  useGeneratedReports: () => ({ data: { items: mocks.generatedReports, total: mocks.generatedReports.length, page: 1, page_size: 10 }, isLoading: false, isFetching: false, refetch: mocks.refetch }),
  useGenerateReport: () => ({ mutateAsync: mocks.generateReport, isPending: false, error: null }),
  useDeleteGeneratedReport: () => ({ mutateAsync: mocks.deleteReport, isPending: false, error: null }),
  useDeleteGeneratedReports: () => ({ mutateAsync: mocks.deleteReports, isPending: false, error: null }),
  useSavedReportTemplates: () => ({ data: [], isLoading: false }),
}));

describe('ReportsView', () => {
  const renderView = () => render(<MemoryRouter><ReportsView /></MemoryRouter>);
  beforeEach(() => {
    mocks.canExport = true;
    mocks.refetch.mockReset();
    mocks.generateReport.mockReset();
    mocks.generateReport.mockResolvedValue({ name: 'June 2026 - Executive Performance Report' });
    mocks.deleteReport.mockReset();
    mocks.deleteReports.mockReset();
    mocks.deleteReport.mockResolvedValue({ id: 'report-1', name: 'June Team Report' });
    mocks.deleteReports.mockResolvedValue({ count: 2, items: [] });
    mocks.generatedReports = [];
  });

  it('renders backend templates and the authorized reporting period', () => {
    renderView();

    expect(screen.getByRole('heading', { name: 'PowerPoint reports', level: 1 })).toBeInTheDocument();
    expect(screen.getByText('Executive Performance Report')).toBeInTheDocument();
    expect(screen.getByText('Team Performance Report')).toBeInTheDocument();
    expect(screen.getAllByText('PPTX').length).toBeGreaterThan(0);
    expect(screen.getByRole('combobox', { name: 'Select Reporting Period' })).toHaveValue('2026-06');
    expect(screen.getAllByRole('button', { name: /Generate PPTX/i })).toHaveLength(3);
    expect(screen.getByRole('heading', { name: 'Report filters' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Choose a report type' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Priority insights' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'KPI health and gaps' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Corrective actions' })).not.toBeInTheDocument();
  });

  it('shows employee names and exposes an explicit all-level scope', () => {
    renderView();

    const levelFilter = screen.getByRole('combobox', { name: 'Performance level' });
    expect(levelFilter).toHaveValue('');
    expect(screen.getByRole('option', { name: 'All levels' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Managerial' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Corporate' })).toBeInTheDocument();

    const employeeFilter = screen.getByRole('combobox', { name: 'Employee' });
    expect(screen.getByRole('option', { name: 'Alice Smith' })).toHaveValue('EMP1');
    expect(screen.queryByRole('option', { name: 'EMP1' })).not.toBeInTheDocument();
    expect(employeeFilter).toHaveValue('');
  });

  it('generates a PowerPoint directly from the active filters', async () => {
    const user = userEvent.setup();
    renderView();

    await user.click(screen.getByRole('button', { name: 'Generate PPTX for Executive Performance Report' }));

    await waitFor(() => expect(mocks.generateReport).toHaveBeenCalledWith(expect.objectContaining({
      report_type: 'executive',
      start_month: 'June',
      start_year: 2026,
      output_format: 'pptx',
    })));
    expect(screen.getByText('June 2026 - Executive Performance Report generated as a PowerPoint. Download it from history.')).toBeInTheDocument();
  });

  it('applies a quick filter and reflects the scope on every report type', async () => {
    const user = userEvent.setup();
    renderView();

    await user.click(screen.getByRole('button', { name: 'Marketing' }));

    expect(screen.getByRole('combobox', { name: 'Team' })).toHaveValue('Marketing');
    expect(screen.getByText('June 2026 / All regions / Marketing / All employees in selected scope')).toBeInTheDocument();
    expect(screen.getByText('1 scope filter')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Generate PPTX for Executive Performance Report' }));
    await waitFor(() => expect(mocks.generateReport).toHaveBeenCalledWith(expect.objectContaining({ team: 'Marketing' })));

    await user.click(screen.getByRole('button', { name: 'Remove Team filter' }));
    expect(screen.getByRole('combobox', { name: 'Team' })).toHaveValue('');
  });

  it('passes every active Marketing filter into the generated report configuration', async () => {
    const user = userEvent.setup();
    renderView();

    await user.selectOptions(screen.getByRole('combobox', { name: 'Comparison period' }), '2026-04');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Region' }), 'EGY');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Team' }), 'Marketing');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Performance level' }), 'Employee');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Position' }), 'Analyst');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Employee' }), 'EMP1');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Grade' }), 'A');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Status' }), 'Meets');
    await user.selectOptions(screen.getByRole('combobox', { name: 'KPI' }), 'quality');

    await user.click(screen.getByRole('button', { name: 'Generate PPTX for Marketing Summary - PowerPoint' }));

    await waitFor(() => expect(mocks.generateReport).toHaveBeenCalledWith(expect.objectContaining({
      report_type: 'team_marketing',
      comparison_month: 'April',
      comparison_year: 2026,
      region: 'EGY',
      team: 'Marketing',
      performance_level: 'Employee',
      position: 'Analyst',
      employee_id: 'EMP1',
      grade: 'A',
      status: 'Meets',
      kpi: 'quality',
    })));
  });

  it('sends an unfiltered team scope when All levels is selected', async () => {
    const user = userEvent.setup();
    renderView();

    await user.click(screen.getByRole('button', { name: 'Marketing' }));
    await user.selectOptions(screen.getByRole('combobox', { name: 'Performance level' }), 'Employee');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Performance level' }), '');
    await user.click(screen.getByRole('button', { name: 'Generate PPTX for Marketing Summary - PowerPoint' }));

    await waitFor(() => expect(mocks.generateReport).toHaveBeenCalledWith(expect.objectContaining({
      report_type: 'team_marketing',
      team: 'Marketing',
      performance_level: null,
      employee_id: null,
    })));
  });

  it('shows preview-only state when the authenticated role cannot export', () => {
    mocks.canExport = false;
    renderView();

    expect(screen.getByText('Preview only - report generation is unavailable for your role.')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Preview only' })).toHaveLength(3);
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

  it('selects multiple reports and deletes them in one confirmation', async () => {
    const user = userEvent.setup();
    mocks.generatedReports = [
      {
        id: 'report-1',
        name: 'June Team Report',
        report_type: 'team',
        period: 'June 2026',
        created_at: '2026-07-22T16:09:00Z',
        format: 'pptx',
        file_name: 'June_Team_Report.pptx',
        download_url: '/api/reports/report-1/download',
      },
      {
        id: 'report-2',
        name: 'July Team Report',
        report_type: 'team',
        period: 'July 2026',
        created_at: '2026-08-22T16:09:00Z',
        format: 'pdf',
        file_name: 'July_Team_Report.pdf',
        download_url: '/api/reports/report-2/download',
      },
    ];
    renderView();

    await user.click(screen.getByRole('checkbox', { name: 'Select June Team Report' }));
    await user.click(screen.getByRole('checkbox', { name: 'Select July Team Report' }));
    await user.click(screen.getByRole('button', { name: 'Delete 2 selected reports' }));

    expect(screen.getByRole('alertdialog', { name: 'Delete 2 reports?' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Delete reports' }));

    await waitFor(() => expect(mocks.deleteReports).toHaveBeenCalledWith(['report-1', 'report-2']));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(screen.getByText('2 reports deleted successfully.')).toBeInTheDocument();
  });
});
