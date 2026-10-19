import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useInsightsExport } from './useInsightsExport';
import type { InsightsWorkspace } from '../../features/insights/types';

describe('useInsightsExport', () => {
  it('returns idle state initially', () => {
    const { result } = renderHook(() =>
      useInsightsExport({
        filters: {},
        workspace: null,
        effectivePeriod: '2026-06',
        fetchWithRole: vi.fn(),
      })
    );

    expect(result.current.exportState).toBe('idle');
    expect(result.current.exportError).toBeNull();
  });

  it('sets error state when effective period is not found in workspace options', async () => {
    const workspace = {
      options: {
        periods: [{ key: '2026-05', year: 2026, month: 'May' }],
      },
    } as unknown as InsightsWorkspace;

    const { result } = renderHook(() =>
      useInsightsExport({
        filters: {},
        workspace,
        effectivePeriod: '2026-06',
        fetchWithRole: vi.fn(),
      })
    );

    await act(async () => {
      await result.current.handleExport();
    });

    expect(result.current.exportState).toBe('error');
    expect(result.current.exportError).toBe('The selected Insights period is unavailable for export.');
  });
});
