import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../lib/apiClient';
import { performanceSessionKey } from '../../lib/performanceSessionKey';
import { mapScopedPerformanceRecord } from '../../hooks/usePerformanceData';

/** Uses the canonical employee and management scoring sources with server-side access scope. */
export function useSummaryRecords(enabled: boolean, employeeId?: string) {
  return useQuery({
    queryKey: ['performance', 'summary-records', employeeId ?? 'all', performanceSessionKey()],
    queryFn: async ({ signal }) => {
      const query = employeeId ? `?employee_id=${encodeURIComponent(employeeId)}` : '';
      const response = await apiFetch<{ success: boolean; data: Parameters<typeof mapScopedPerformanceRecord>[0][]; message?: string }>(`/api/performance/summary-records${query}`, { signal });
      if (!response.success || !Array.isArray(response.data)) throw new Error(response.message || 'Summary evidence could not be loaded.');
      return response.data.map(mapScopedPerformanceRecord);
    },
    enabled,
    retry: false,
    staleTime: 2 * 60_000,
  });
}
