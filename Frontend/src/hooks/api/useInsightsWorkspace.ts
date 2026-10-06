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
  if (filters.region) params.set('region', filters.region);
  // `function` (live since PR #14) expands to the function's source teams with
  // the same `_team_keys` rules and access checks as a parent `team` value; a
  // selected team narrows further. Report export and quick-action team data
  // only accept `team`, so they keep `apiTeamParam` (identical expansion).
  if (filters.teamFunction) params.set('function', filters.teamFunction);
  if (filters.team) params.set('team', filters.team);
  const mappings: Array<[keyof InsightFilters, string]> = [
    ['performanceLevel', 'performance_level'],
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
    queryFn: async ({ signal }) => (
      await apiFetch<ApiResponse<InsightsWorkspace>>(insightsWorkspaceUrl(filters, view), { signal })
    ).data,
    placeholderData: (previous) => previous,
    enabled: options.enabled ?? true,
  });
}
