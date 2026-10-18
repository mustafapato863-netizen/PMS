import { useQuery } from '@tanstack/react-query';
import type { InsightFilters, InsightsWorkspace } from '../../features/insights/types';
import { apiFetch } from '../../lib/apiClient';

interface ApiResponse<T> {
  success: boolean;
  message: string;
  data: T;
}

/** A field of the workspace response that a request can ask for. Mirrors the backend's WORKSPACE_SECTIONS. */
export type InsightSection =
  | 'summary' | 'priority_insights' | 'team_analyses' | 'performance_drivers' | 'risks' | 'opportunities'
  | 'data_issues' | 'team_summaries' | 'geography_summaries' | 'executive_story' | 'people_contribution_analysis'
  | 'kpi_trend' | 'overall_trend' | 'role_summaries' | 'kpi_overview' | 'kpi_diagnosis' | 'tracking_indicators'
  | 'options' | 'comparison' | 'deferred_capabilities';

/** The fields the Insights page renders. Keep in step with what InsightsView and its components read. */
export const INSIGHTS_PAGE_SECTIONS: readonly InsightSection[] = [
  'options', 'comparison', 'executive_story', 'priority_insights', 'people_contribution_analysis',
  'kpi_trend', 'kpi_diagnosis', 'tracking_indicators',
];

export function insightsWorkspaceUrl(
  filters: InsightFilters,
  view: 'full' | 'priority' = 'full',
  sections?: readonly InsightSection[],
) {
  const params = new URLSearchParams();
  if (filters.periodKey) {
    const [year, monthNumber] = filters.periodKey.split('-').map(Number);
    const month = new Intl.DateTimeFormat('en-US', { month: 'long', timeZone: 'UTC' })
      .format(new Date(Date.UTC(year, monthNumber - 1, 1)));
    params.set('year', String(year));
    params.set('month', month);
  }
  if (filters.region) params.set('region', filters.region);
  if (filters.branch) params.set('branch', filters.branch);
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
  if (sections?.length) params.set('sections', sections.join(','));
  if (view === 'priority') params.set('view', view);
  const query = params.toString();
  return `/api/insights/workspace${query ? `?${query}` : ''}`;
}

/** A request for some sections has its own cache entry. Without sections the key is the one it always was. */
export function insightsWorkspaceQueryKey(
  filters: InsightFilters,
  view: 'full' | 'priority' = 'full',
  sections?: readonly InsightSection[],
) {
  return sections?.length
    ? (['insights', 'workspace', view, filters, { sections: sections.join(',') }] as const)
    : (['insights', 'workspace', view, filters] as const);
}

export function useInsightsWorkspace(
  filters: InsightFilters,
  options: { enabled?: boolean; view?: 'full' | 'priority'; sections?: readonly InsightSection[] } = {},
) {
  const view = options.view ?? 'full';
  const sections = options.sections?.length ? options.sections : undefined;
  return useQuery({
    queryKey: insightsWorkspaceQueryKey(filters, view, sections),
    queryFn: async ({ signal }) => (
      await apiFetch<ApiResponse<InsightsWorkspace>>(insightsWorkspaceUrl(filters, view, sections), { signal })
    ).data,
    placeholderData: (previous) => previous,
    enabled: options.enabled ?? true,
  });
}
