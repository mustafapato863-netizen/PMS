import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useReportBuilderStore } from './reportBuilderStore';
import type { StoryReportDraft } from '../features/reports/types';

const draft: StoryReportDraft = {
  id: 'draft-1', name: 'June Review', report_type: 'executive', template_id: 'template-1', template_version: 1,
  owner_user_id: 'user-1', status: 'editing', primary_period: { month: 'June', year: 2026 },
  comparison_period: { month: 'May', year: 2026 }, scope: { team: 'Inbound' }, version: 3,
  last_saved_at: null, updated_at: null, validation: null,
  management_commentary: { entries: { commentary: '' } },
  definition: {
    theme_key: 'sgh_default', language: 'en', preferred_format: 'pdf', narratives: {},
    slides: [{ id: 'page-1', title: 'Executive Summary', layout: 'full_width', order: 0, blocks: [{
      id: 'block-1', type: 'executive_kpi_summary', slot: 'full', config: {
        title: null, metrics: [], comparison: true, number_format: 'standard', row_limit: 10,
        sort_by: null, sort_direction: 'desc', show_icons: true, show_subtitle: true,
        show_data_labels: true, show_target: true, narrative_mode: 'auto', include_evidence: true,
        include_recommendations: true, max_length: 700, scope_override: {},
      },
    }] }],
  },
};

describe('reportBuilderStore', () => {
  beforeEach(() => {
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => 'new-id') });
    useReportBuilderStore.getState().reset();
  });

  it('hydrates the complete persisted story instead of inventing browser slides', () => {
    useReportBuilderStore.getState().loadDraft(draft);
    const state = useReportBuilderStore.getState();
    expect(state.draftId).toBe('draft-1');
    expect(state.draftVersion).toBe(3);
    expect(state.slides).toEqual(draft.definition.slides);
    expect(state.currentStep).toBe(3);
    expect(state.saveState).toBe('saved');
  });

  it('marks structural and management-commentary edits dirty without mixing narratives', () => {
    useReportBuilderStore.getState().loadDraft(draft);
    useReportBuilderStore.getState().updateSlide('page-1', { title: 'Updated Summary' });
    useReportBuilderStore.getState().setCommentary('commentary', 'Manager-confirmed context');
    const state = useReportBuilderStore.getState();
    expect(state.slides[0].title).toBe('Updated Summary');
    expect(state.commentary.entries.commentary).toBe('Manager-confirmed context');
    expect(state.definition.narratives).toEqual({});
    expect(state.saveState).toBe('dirty');
  });
});
