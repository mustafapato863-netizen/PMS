import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { useReportBuilderStore } from '../../../store/reportBuilderStore';
import Step2Template from './Step2Template';

const mocks = vi.hoisted(() => ({
  refetch: vi.fn(),
  mutateAsync: vi.fn(),
  templates: undefined as unknown,
  error: null as Error | null,
}));

vi.mock('../../../hooks/api/useReports', () => ({
  useStoryTemplates: () => ({ data: mocks.templates, isLoading: false, error: mocks.error, refetch: mocks.refetch }),
  useReportOptions: () => ({ data: { employees: [
    { id: '1', name: 'A', team: 'Inbound', region: 'EGY', position: '', performance_level: '' },
    { id: '2', name: 'B', team: 'Outbound', region: 'EGY', position: '', performance_level: '' },
    { id: '3', name: 'C', team: 'Pre-Approvals', region: 'EGY', position: '', performance_level: '' },
  ] } }),
  useCreateStoryDraft: () => ({ mutateAsync: mocks.mutateAsync, isPending: false, error: null }),
}));

const fullTemplate = {
  id: 'template-full', name: 'Full Monthly Performance Review', template_key: 'offshore_monthly_performance_review',
  report_type: 'executive', description: 'Evidence to decision story.', visibility: 'organization', version: 2,
  theme_key: 'sgh_default', language: 'en', preferred_format: 'pdf', is_system_template: true,
  updated_at: null, page_count: 15,
  definition: {
    slides: [], theme_key: 'sgh_default', language: 'en', preferred_format: 'pdf',
    story_metadata: { mode: 'full', fixed_page_count: 14, pages_per_team: 1, recommended: true, outline: ['Executive context', 'Team reviews'] },
  },
};

describe('Step2Template', () => {
  beforeEach(() => {
    mocks.refetch.mockReset();
    mocks.mutateAsync.mockReset();
    mocks.templates = undefined;
    mocks.error = null;
    useReportBuilderStore.getState().reset();
    useReportBuilderStore.getState().setConfiguration({ report_name: 'June Review', start_month: 'June', start_year: 2026, end_month: 'May', end_year: 2026, region: 'EGY' });
  });

  it('shows the backend error and lets the user retry without leaving the workflow', async () => {
    mocks.error = new Error('Template service unavailable');
    const user = userEvent.setup();
    render(<MemoryRouter><Step2Template /></MemoryRouter>);

    expect(screen.getByRole('alert')).toHaveTextContent('Template service unavailable');
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(mocks.refetch).toHaveBeenCalledOnce();
  });

  it('previews the filtered story and shows the scope-aware page estimate before creation', async () => {
    mocks.templates = [fullTemplate];
    const user = userEvent.setup();
    render(<MemoryRouter><Step2Template /></MemoryRouter>);

    expect(screen.getByText('17 pages')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Preview story/i }));
    expect(screen.getByRole('dialog')).toHaveTextContent('Executive context');
    expect(screen.getByRole('dialog')).toHaveTextContent('17 pages');
    expect(screen.getByRole('button', { name: /Use Template/i })).toBeInTheDocument();
    expect(mocks.mutateAsync).not.toHaveBeenCalled();
  });
});
