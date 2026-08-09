import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../lib/apiClient';

export interface PerformanceCatalog {
  periods: Array<{ year: number; month: string; key: string }>;
  months: string[];
  scopes: Array<{
    team: string;
    region: string | null;
    performance_level: string;
    position: string | null;
  }>;
}

export function usePerformanceCatalog() {
  return useQuery({
    queryKey: ['performance', 'catalog'],
    queryFn: async () => (
      await apiFetch<{ success: boolean; data: PerformanceCatalog }>('/api/performance/catalog')
    ).data,
    staleTime: 10 * 60 * 1000,
  });
}
