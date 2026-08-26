import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../lib/apiClient';
import type { AgentRecord } from '../../types';
import type { MarketingTeamConfig } from './types';
import { mapScopedPerformanceRecord } from '../../hooks/usePerformanceData';
import { scopedPerformanceApiEnabled } from '../../hooks/api/usePerformanceDashboard';
import { usePerformanceCatalog } from '../../hooks/api/usePerformanceCatalog';

type ScopedMarketingPage = {
  items: Array<Record<string, unknown>>;
  next_cursor?: string | null;
  has_more?: boolean;
};

function sessionCacheKey(): string {
  try {
    const saved = localStorage.getItem('pms_session_v1');
    if (!saved) return 'anonymous';
    const user = JSON.parse(saved) as { id?: string; username?: string };
    return user.id || user.username || 'anonymous';
  } catch {
    return 'anonymous';
  }
}

export const useMarketingData = () => {
  const catalogQuery = usePerformanceCatalog(scopedPerformanceApiEnabled);
  const configQuery = useQuery({
    queryKey: ['marketing-config'],
    queryFn: async () => {
      const response = await apiFetch<{ success: boolean; data: MarketingTeamConfig }>(
        '/api/config/teams/Marketing?performance_level=Employee',
      );
      return response.data;
    },
    staleTime: Infinity,
  });

  const recordsQuery = useQuery({
    queryKey: ['marketing-performance', sessionCacheKey(), scopedPerformanceApiEnabled, catalogQuery.data?.periods],
    queryFn: async () => {
      if (scopedPerformanceApiEnabled) {
        const records: AgentRecord[] = [];
        for (const period of (catalogQuery.data?.periods || []).slice(0, 24)) {
          let cursor: string | undefined;
          let pageCount = 0;
          do {
            const params = new URLSearchParams({
              period: period.key,
              team: 'Marketing',
              performance_level: 'Employee',
              detail: 'full',
              page_size: '100',
            });
            if (cursor) params.set('cursor', cursor);
            const response = await apiFetch<{
              success: boolean;
              data?: ScopedMarketingPage;
              message?: string;
            }>(`/api/performance/records?${params.toString()}`);
            if (!response.success || !response.data) {
              throw new Error(response.message || 'Marketing performance request failed');
            }
            records.push(...(response.data.items || []).map(mapScopedPerformanceRecord));
            cursor = response.data.has_more && response.data.next_cursor
              ? response.data.next_cursor
              : undefined;
            pageCount += 1;
            if (pageCount >= 1000 && cursor) {
              throw new Error('Marketing performance pagination exceeded the safety limit');
            }
          } while (cursor);
        }
        return records;
      }
      const response = await apiFetch<{ success: boolean; data: AgentRecord[] }>(
        '/api/performance?team=Marketing&performance_level=Employee',
      );
      if (!response.success || !Array.isArray(response.data)) {
        throw new Error('Marketing performance request failed');
      }
      return response.data;
    },
    enabled: !scopedPerformanceApiEnabled || Boolean(catalogQuery.data),
    staleTime: 2 * 60 * 1000,
  });

  return {
    config: configQuery.data,
    records: recordsQuery.data || [],
    loading: configQuery.isLoading || catalogQuery.isLoading || recordsQuery.isLoading,
    error: configQuery.error || catalogQuery.error || recordsQuery.error,
    refetch: async () => {
      await Promise.all([configQuery.refetch(), catalogQuery.refetch(), recordsQuery.refetch()]);
    },
  };
};
