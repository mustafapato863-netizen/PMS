import { describe, expect, it } from 'vitest';
import type { StoryBlockRegistryItem, StoryLayoutRegistryItem, StoryReportBlock } from './types';
import { assignBlocksToLayout, bestLayoutAssignment, compatibleLayoutAssignments } from './reportBuilderLayout';

const registryBlocks: StoryBlockRegistryItem[] = [
  { type: 'executive_kpi_summary', name: 'Summary', category: 'Summary', description: '', icon: '', provider: '', slots: ['summary', 'full'], permissions: [] },
  { type: 'score_trend', name: 'Score Trend', category: 'Performance', description: '', icon: '', provider: '', slots: ['chart', 'full'], permissions: [] },
  { type: 'system_analysis', name: 'System Analysis', category: 'Narrative', description: '', icon: '', provider: '', slots: ['narrative', 'full'], permissions: [] },
];

const layouts: StoryLayoutRegistryItem[] = [
  { key: 'full_width', max_blocks: 1, slots: { full: ['Summary', 'Performance', 'Narrative'] } },
  { key: 'two_blocks', max_blocks: 2, slots: { left: ['Summary', 'Performance', 'Narrative'], right: ['Summary', 'Performance', 'Narrative'] } },
  { key: 'kpi_chart', max_blocks: 2, slots: { summary: ['Summary'], chart: ['Performance'] } },
  { key: 'kpi_chart_narrative', max_blocks: 3, slots: { summary: ['Summary'], chart: ['Performance'], narrative: ['Narrative'] } },
];

const block = (id: string, type: string, slot = 'full'): StoryReportBlock => ({
  id,
  type,
  slot,
  config: {
    title: null,
    metrics: [],
    comparison: true,
    number_format: 'standard',
    row_limit: 10,
    sort_by: null,
    sort_direction: 'desc',
    show_icons: true,
    show_subtitle: true,
    show_data_labels: true,
    show_target: true,
    narrative_mode: 'auto',
    include_evidence: true,
    include_recommendations: true,
    max_length: 700,
    scope_override: {},
  },
});

describe('report builder layout placement', () => {
  it('moves an existing full-width block into a compatible multi-block layout', () => {
    const blocks = [block('summary', 'executive_kpi_summary'), block('trend', 'score_trend', '')];
    const assignment = bestLayoutAssignment(blocks, layouts, registryBlocks, 'full_width');

    expect(assignment?.layout.key).toBe('two_blocks');
    expect(assignment?.blocks.map((item) => item.slot)).toEqual(['left', 'right']);
  });

  it('preserves a valid slot and rejects layouts that cannot fit every block', () => {
    const summary = block('summary', 'executive_kpi_summary', 'summary');
    expect(assignBlocksToLayout([summary], layouts[2], registryBlocks)?.[0].slot).toBe('summary');
    expect(compatibleLayoutAssignments([summary, block('analysis', 'system_analysis')], layouts, registryBlocks).map(({ layout }) => layout.key)).toEqual(['two_blocks', 'kpi_chart_narrative']);
  });
});
