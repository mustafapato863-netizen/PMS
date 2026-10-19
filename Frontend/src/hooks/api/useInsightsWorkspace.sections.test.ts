import { describe, expect, it } from 'vitest';
import { INSIGHTS_PAGE_SECTIONS, insightsWorkspaceQueryKey, insightsWorkspaceUrl } from './useInsightsWorkspace';

const filters = { periodKey: '2026-06', team: 'Outbound' };

describe('insights workspace sections', () => {
  it('requests only the listed sections, as one comma-separated parameter', () => {
    const url = new URL(insightsWorkspaceUrl(filters, 'full', INSIGHTS_PAGE_SECTIONS), 'http://pms.test');

    expect(url.searchParams.get('sections')).toBe(INSIGHTS_PAGE_SECTIONS.join(','));
    expect(url.searchParams.get('team')).toBe('Outbound');
    expect(url.searchParams.get('month')).toBe('June');
  });

  it('sends no sections parameter when none are given, so every field is computed as before', () => {
    expect(new URL(insightsWorkspaceUrl(filters), 'http://pms.test').searchParams.has('sections')).toBe(false);
    expect(new URL(insightsWorkspaceUrl(filters, 'full', []), 'http://pms.test').searchParams.has('sections')).toBe(false);
  });

  it('keys the cache by the sections requested, and keeps the existing key without them', () => {
    expect(insightsWorkspaceQueryKey(filters)).toEqual(['insights', 'workspace', 'full', filters]);

    const page = insightsWorkspaceQueryKey(filters, 'full', INSIGHTS_PAGE_SECTIONS);
    expect(page).not.toEqual(insightsWorkspaceQueryKey(filters));
    expect(page).toContainEqual({ sections: INSIGHTS_PAGE_SECTIONS.join(',') });
    expect(insightsWorkspaceQueryKey(filters, 'full', ['options'])).not.toEqual(page);
  });

  it('asks for the nine fields the Insights page renders', () => {
    expect([...INSIGHTS_PAGE_SECTIONS].sort()).toEqual([
      'comparison',
      'executive_story',
      'kpi_diagnosis',
      'kpi_trend',
      'options',
      'people_contribution_analysis',
      'priority_insights',
      'summary',
      'tracking_indicators',
    ]);
  });
});
