import { describe, expect, it } from 'vitest';
import { insightsWorkspaceUrl } from './useInsightsWorkspace';

describe('insightsWorkspaceUrl', () => {
  it('preserves the existing full-workspace URL contract by default', () => {
    expect(insightsWorkspaceUrl({
      periodKey: '2026-06',
      team: 'Outbound',
    })).toBe('/api/insights/workspace?year=2026&month=June&team=Outbound');
  });

  it('requests the compact priority view explicitly', () => {
    expect(insightsWorkspaceUrl({
      periodKey: '2026-06',
      team: 'Outbound',
    }, 'priority')).toBe(
      '/api/insights/workspace?year=2026&month=June&team=Outbound&view=priority',
    );
  });
});
