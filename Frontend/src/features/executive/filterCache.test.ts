import { beforeEach, describe, expect, it } from 'vitest';
import {
  clearCachedExecutiveFilters,
  readCachedExecutiveFilters,
  saveCachedExecutiveFilters,
} from './filterCache';
import {
  EXECUTIVE_SUMMARY_SECTIONS,
  insightsWorkspaceQueryKey,
  insightsWorkspaceUrl,
} from '../../hooks/api/useInsightsWorkspace';

describe('Executive Summary frontend caching helpers', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('persists active filters and clears sessionStorage when every filter resets to All', () => {
    saveCachedExecutiveFilters({ period: '2026-09', region: 'EGY', level: 'Employee' });
    expect(readCachedExecutiveFilters()).toEqual({
      period: '2026-09',
      region: 'EGY',
      level: 'Employee',
    });

    // Manually resetting all filters back to "All" must remove stale cached entries.
    saveCachedExecutiveFilters({ period: 'All', region: 'all', branch: undefined, level: 'All' });
    expect(readCachedExecutiveFilters()).toBeNull();

    saveCachedExecutiveFilters({ region: 'UAE' });
    clearCachedExecutiveFilters();
    expect(readCachedExecutiveFilters()).toBeNull();
  });

  it('scopes insights workspace query keys by session and minimal Executive Summary sections', () => {
    const keyWithSections = insightsWorkspaceQueryKey(
      { periodKey: '2026-09', performanceLevel: 'Employee' },
      'full',
      EXECUTIVE_SUMMARY_SECTIONS,
    );
    const keyWithoutSections = insightsWorkspaceQueryKey(
      { periodKey: '2026-09', performanceLevel: 'Employee' },
      'full',
    );
    expect(keyWithSections[0]).toBe('insights');
    expect(keyWithSections[1]).toBe('workspace');
    expect(typeof keyWithSections[3]).toBe('string');
    expect(keyWithSections).not.toEqual(keyWithoutSections);

    const url = insightsWorkspaceUrl(
      { periodKey: '2026-09', performanceLevel: 'Employee' },
      'full',
      EXECUTIVE_SUMMARY_SECTIONS,
    );
    expect(url).toContain('performance_level=Employee');
    expect(url).toContain('sections=options%2Cperformance_drivers%2Cteam_analyses%2Cpriority_insights%2Copportunities');
  });
});
