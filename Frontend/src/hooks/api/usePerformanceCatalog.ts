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
  data_version?: number;
  as_of?: string;
}

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

export function usePerformanceCatalog(enabled = true) {
  const session = sessionCacheKey();
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
