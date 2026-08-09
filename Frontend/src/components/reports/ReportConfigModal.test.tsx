import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import ReportConfigModal from './ReportConfigModal';

vi.mock('../../hooks/api/useReports', () => {
  const mutation = () => ({
    data: undefined,
    error: null,
    isPending: false,
    mutate: vi.fn(),
    reset: vi.fn(),
  });
  return {
    usePreviewReport: mutation,
    useGenerateReport: mutation,
    useSaveReportTemplate: mutation,
  };
});

const template = {
  type: 'kpi' as const,
  category: 'kpi',
  name: 'KPI Performance Report',
  description: 'KPI detail',
  formats: ['pptx' as const, 'pdf' as const],
  sections: ['summary'],
};

const options = {
  periods: [{ year: 2026, month: 'June', key: '2026-06' }],
  teams: [],
  regions: [],
  performance_levels: [],
  positions: [],
  employees: [],
  grades: [],
  statuses: [],
  can_export: true,
};

const configuration = {
  report_type: 'kpi' as const,
  report_name: 'June KPI report',
  start_month: 'June',
  start_year: 2026,
  included_sections: ['summary'],
  output_format: 'pptx' as const,
};

describe('ReportConfigModal', () => {
  it('renders at the document root above the application stacking context', () => {
    const { container, unmount } = render(
      <ReportConfigModal
        template={template}
        options={options}
        initialConfiguration={configuration}
        onClose={vi.fn()}
        onGenerated={vi.fn()}
      />,
    );

    const dialog = screen.getByRole('dialog', { name: 'KPI Performance Report' });
    expect(container).not.toContainElement(dialog);
    expect(document.body).toContainElement(dialog);
    expect(dialog.parentElement).toHaveClass('z-[100]');
    expect(document.body.style.overflow).toBe('hidden');
    expect(screen.getByText('PowerPoint is selected by default.')).toBeInTheDocument();

    unmount();
    expect(document.body.style.overflow).toBe('');
  });
});
