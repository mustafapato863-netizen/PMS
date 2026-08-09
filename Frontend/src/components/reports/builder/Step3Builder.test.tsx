import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { StoryReportDraft } from '../../../features/reports/types';
import { useReportBuilderStore } from '../../../store/reportBuilderStore';
import Step3Builder from './Step3Builder';

vi.mock('../../../hooks/api/useReports', () => ({
  useStoryRegistry: () => ({
    data: {
      categories: ['All', 'Summary', 'Performance'],
      blocks: [
        { type: 'executive_kpi_summary', name: 'Executive KPI Summary', category: 'Summary', description: 'Summary', icon: '', provider: 'summary', slots: ['summary', 'full'], permissions: [] },
        { type: 'score_trend', name: 'Score Trend', category: 'Performance', description: 'Trend', icon: '', provider: 'trend', slots: ['chart', 'full'], permissions: [] },
      ],
      layouts: [
        { key: 'full_width', max_blocks: 1, slots: { full: ['Summary', 'Performance'] } },
        { key: 'two_blocks', max_blocks: 2, slots: { left: ['Summary', 'Performance'], right: ['Summary', 'Performance'] } },
        { key: 'kpi_chart', max_blocks: 2, slots: { summary: ['Summary'], chart: ['Performance'] } },
      ],
    },
  }),
  useStoryPage: () => ({ data: undefined, isFetching: false }),
  usePrefetchStoryPage: () => vi.fn(() => Promise.resolve()),
}));

const config = {
  title: null,
  metrics: [],
  comparison: true,
  number_format: 'standard' as const,
  row_limit: 10,
  sort_by: null,
  sort_direction: 'desc' as const,
  show_icons: true,
  show_subtitle: true,
  show_data_labels: true,
  show_target: true,
  narrative_mode: 'auto' as const,
  include_evidence: true,
  include_recommendations: true,
  max_length: 700,
  scope_override: {},
};

const draft: StoryReportDraft = {
  id: 'draft-1',
  name: 'June Review',
  report_type: 'executive',
  template_id: 'template-1',
  template_version: 1,
  owner_user_id: 'user-1',
  status: 'editing',
  primary_period: { month: 'June', year: 2026 },
  comparison_period: { month: 'May', year: 2026 },
  scope: {},
  version: 1,
  last_saved_at: null,
  updated_at: null,
  validation: null,
  management_commentary: { entries: {} },
  definition: {
    theme_key: 'sgh_default',
    language: 'en',
    preferred_format: 'pdf',
    narratives: {},
    slides: [{
      id: 'page-1',
      title: 'Executive Summary',
      layout: 'full_width',
      order: 0,
      blocks: [{ id: 'summary', type: 'executive_kpi_summary', slot: 'full', config }],
    }],
  },
};

describe('Step3Builder multi-block pages', () => {
  beforeEach(() => {
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'trend') });
    useReportBuilderStore.getState().reset();
    useReportBuilderStore.getState().loadDraft(draft);
  });

  it('adds a second block and switches to the best compatible layout', async () => {
    const user = userEvent.setup();
    render(<Step3Builder />);

    await user.click(screen.getByRole('button', { name: 'Add Block' }));
    expect(screen.getByText(/best compatible multi-block layout/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Score Trend/i }));

    const page = useReportBuilderStore.getState().slides[0];
    expect(page.layout).toBe('two_blocks');
    expect(page.blocks.map((item) => [item.type, item.slot])).toEqual([
      ['executive_kpi_summary', 'left'],
      ['score_trend', 'right'],
    ]);
  });

  it('can add a governed block as a separate page when the current page should stay focused', async () => {
    const user = userEvent.setup();
    render(<Step3Builder />);

    await user.click(screen.getByRole('button', { name: /Block as page/i }));
    await user.click(screen.getByRole('button', { name: /Score Trend/i }));

    const pages = useReportBuilderStore.getState().slides;
    expect(pages).toHaveLength(2);
    expect(pages[1]).toMatchObject({ title: 'Score Trend', layout: 'full_width' });
    expect(pages[1].blocks[0]).toMatchObject({ type: 'score_trend', slot: 'full' });
  });

  it('uses an accessible product dialog before deleting a page', async () => {
    const user = userEvent.setup();
    render(<Step3Builder />);

    await user.click(screen.getByRole('button', { name: 'Delete Executive Summary' }));
    expect(screen.getByRole('alertdialog', { name: /Delete “Executive Summary”/i })).toBeInTheDocument();
    expect(screen.getByText(/page and its 1 block will be removed/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Keep page' }));
    expect(useReportBuilderStore.getState().slides).toHaveLength(1);

    await user.click(screen.getByRole('button', { name: 'Delete Executive Summary' }));
    await user.click(screen.getByRole('button', { name: 'Delete page' }));
    expect(useReportBuilderStore.getState().slides).toHaveLength(0);
  });
});
