import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../lib/apiClient';
import { performanceSessionKey } from '../../lib/performanceSessionKey';

export interface PerformanceCatalog {
  periods: Array<{ year: number; month: string; key: string }>;
  months: string[];
  scopes: Array<{
    team: string;
    region: string | null;
    performance_level: string;
    position: string | null;
  }>;
  data_version?: number;
  as_of?: string;
}

export function usePerformanceCatalog(enabled = true) {
  const session = performanceSessionKey();
  return useQuery({
    queryKey: ['performance', 'catalog', session],
    queryFn: async () => {
      const response = await apiFetch<{ success: boolean; data?: PerformanceCatalog; message?: string }>('/api/performance/catalog');
      if (!response.success || !response.data) {
        throw new Error(response.message || 'Performance catalog request failed');
      }
      return response.data;
    },
    staleTime: 10 * 60 * 1000,
    enabled,
  });
}
