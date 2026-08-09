import { useQuery } from '@tanstack/react-query';
import type { InsightFilters, InsightsWorkspace } from '../../features/insights/types';
import { apiFetch } from '../../lib/apiClient';

interface ApiResponse<T> {
  success: boolean;
  message: string;
  data: T;
}

export function insightsWorkspaceUrl(filters: InsightFilters, view: 'full' | 'priority' = 'full') {
  const params = new URLSearchParams();
  if (filters.periodKey) {
    const [year, monthNumber] = filters.periodKey.split('-').map(Number);
    const month = new Intl.DateTimeFormat('en-US', { month: 'long', timeZone: 'UTC' })
      .format(new Date(Date.UTC(year, monthNumber - 1, 1)));
    params.set('year', String(year));
    params.set('month', month);
  }
  const mappings: Array<[keyof InsightFilters, string]> = [
    ['region', 'region'], ['team', 'team'], ['performanceLevel', 'performance_level'],
    ['position', 'position'], ['employeeId', 'employee_id'], ['kpi', 'kpi'],
    ['severity', 'severity'], ['insightType', 'insight_type'], ['status', 'status'],
  ];
  mappings.forEach(([key, parameter]) => {
    const value = filters[key];
    if (value) params.set(parameter, value);
  });
  if (view === 'priority') params.set('view', view);
  const query = params.toString();
  return `/api/insights/workspace${query ? `?${query}` : ''}`;
}

export function useInsightsWorkspace(
  filters: InsightFilters,
  options: { enabled?: boolean; view?: 'full' | 'priority' } = {},
) {
  const view = options.view ?? 'full';
  return useQuery({
    queryKey: ['insights', 'workspace', view, filters],
    queryFn: async () => (
      await apiFetch<ApiResponse<InsightsWorkspace>>(insightsWorkspaceUrl(filters, view))
    ).data,
    placeholderData: (previous) => previous,
    enabled: options.enabled ?? true,
  });
}
