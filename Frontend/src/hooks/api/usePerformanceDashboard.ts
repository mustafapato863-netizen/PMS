import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../lib/apiClient';
import { usePerformanceCatalog } from './usePerformanceCatalog';

export const scopedPerformanceApiEnabled = String(import.meta.env.VITE_SCOPED_PERFORMANCE_API || '').toLowerCase() === 'true';

export interface PerformancePeriod {
  key: string;
  month: string;
  year: number;
}

export interface PerformanceScopeFilters {
  period: string;
  team?: string;
  performance_level?: string;
  region?: string;
  position?: string;
  location?: string;
}

export interface PerformanceSummary {
  scope: PerformanceScopeFilters;
  period: PerformancePeriod;
  previous_period: PerformancePeriod | null;
  current: PerformanceSummaryPeriod;
  previous: PerformanceSummaryPeriod | null;
  trend: Array<PerformancePeriod & PerformanceSummaryPeriod>;
  team_breakdown: PerformanceTeamBreakdown[];
  data_version: number;
  as_of: string;
}

export interface PerformanceSummaryPeriod {
  total_agents: number;
  total_records: number;
  average_score: number;
  weighted_score: number;
  grade_counts: Record<string, number>;
  status_counts: Record<string, number>;
  totals: {
    inbound: number;
    outbound: number;
    total_handled: number;
    abandoned: number;
    bookings: number;
    attended: number;
  };
  rates: {
    booking_rate: number;
    attend_rate: number;
    abandon_rate: number;
    average_aht_seconds: number;
  };
  team_breakdown?: PerformanceTeamBreakdown[];
}

export interface PerformanceTeamBreakdown {
  teamId: string;
  teamName: string;
  agentCount: number;
  avgScore: number;
  classA: number;
  classB: number;
  classC: number;
  classD: number;
  classE: number;
}

export interface PerformanceRecordItem {
  id: string;
  employee_id: string;
  employee_name: string;
  team: string;
  month: string;
  year: number | null;
  region: string | null;
  performance_level: string;
  position: string | null;
  status: string | null;
  score: number;
  grade: string;
  previous_score: number | null;
  trend: number | null;
  [key: string]: unknown;
}

export interface PerformanceRecordPage {
  items: PerformanceRecordItem[];
  page_size: number;
  next_cursor: string | null;
  has_more: boolean;
  total: number | null;
  data_version: number;
  as_of: string;
}

export interface PerformanceRecordFilters extends PerformanceScopeFilters {
  employee_search?: string;
  grade?: string;
  status?: string;
  sort?: 'name' | 'score_desc' | 'score_asc';
  detail?: 'table' | 'full';
  cursor?: string;
  page_size?: number;
  include_total?: boolean;
}

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

export interface ScopedExecutiveSummary {
  summaries: PerformanceTeamBreakdown[];
  previousSummaries: PerformanceTeamBreakdown[];
  totalAgents: number;
  uniqueTeamCount: number;
  overallAvgScore: number;
  pctAB: number;
  pctDE: number;
  allClassCounts: { A: number; B: number; C: number; D: number; E: number };
  uniqueMonths: string[];
  activePeriod: PerformancePeriod | null;
  previousPeriod: PerformancePeriod | null;
  previousTotalAgents: number;
  previousOverallAvgScore: number;
  previousPctAB: number;
  previousPctDE: number;
  loading: boolean;
  dataSource: 'api' | 'empty';
  errorMessage: string | null;
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

function queryString(values: object): string {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  });
  return params.toString();
}

async function fetchData<T>(endpoint: string): Promise<T> {
  const response = await apiFetch<{ success: boolean; data?: T; message?: string }>(endpoint);
  if (!response.success || response.data === undefined) {
    throw new Error(response.message || 'Performance data request failed');
  }
  return response.data;
}

export function usePerformanceSummary(
  filters: PerformanceScopeFilters,
  trendMonths = 12,
) {
  const session = sessionCacheKey();
  const query = queryString({ ...filters, trend_months: trendMonths });
  return useQuery({
    queryKey: ['performance', 'summary', session, filters, trendMonths],
    queryFn: () => fetchData<PerformanceSummary>(`/api/performance/summary?${query}`),
    enabled: scopedPerformanceApiEnabled && Boolean(filters.period),
    placeholderData: keepPreviousData,
    staleTime: 2 * 60 * 1000,
  });
}

export function usePerformanceRecords(filters: PerformanceRecordFilters) {
  const session = sessionCacheKey();
  const query = queryString(filters);
  return useQuery({
    queryKey: ['performance', 'records', session, filters],
    queryFn: () => fetchData<PerformanceRecordPage>(`/api/performance/records?${query}`),
    enabled: scopedPerformanceApiEnabled && Boolean(filters.period),
    placeholderData: keepPreviousData,
    staleTime: 2 * 60 * 1000,
  });
}

export function useScopedEmployeePerformanceHistory(
  employeeId: string | undefined,
  options: {
    period_end?: string;
    months?: number;
    performance_level?: string;
    position?: string;
    region?: string;
  } = {},
) {
  const session = sessionCacheKey();
  const query = queryString(options);
  return useQuery({
    queryKey: ['performance', 'employee-history', session, employeeId, options],
    queryFn: () => fetchData<PerformanceRecordItem[]>(`/api/performance/employee/${encodeURIComponent(employeeId!)}?${query}`),
    enabled: scopedPerformanceApiEnabled && Boolean(employeeId),
    placeholderData: keepPreviousData,
    staleTime: 2 * 60 * 1000,
  });
}

function periodForMonth(catalog: PerformanceCatalog | undefined, month: string): PerformancePeriod | null {
  const periods = (catalog?.periods || [])
    .map((period) => ({ ...period }))
    .sort((left, right) => right.key.localeCompare(left.key));
  if (!periods.length) return null;
  if (!month || month === 'All') return periods[0];
  return periods.find((period) => period.month === month) || periods[0];
}

function toClassCounts(value: Record<string, number> | undefined): { A: number; B: number; C: number; D: number; E: number } {
  return {
    A: Number(value?.A || 0),
    B: Number(value?.B || 0),
    C: Number(value?.C || 0),
    D: Number(value?.D || 0),
    E: Number(value?.E || 0),
  };
}

export function useScopedExecutiveSummary(
  month: string,
  region: string = 'All',
  location: string = 'all',
  performanceLevel: string = 'All',
): ScopedExecutiveSummary {
  const catalogQuery = usePerformanceCatalog(scopedPerformanceApiEnabled);
  const activePeriod = periodForMonth(catalogQuery.data, month);
  const summaryQuery = usePerformanceSummary(
    {
      period: activePeriod?.key || '',
      region: region !== 'All' ? region : undefined,
      location,
      performance_level: performanceLevel !== 'All' ? performanceLevel : undefined,
    },
    24,
  );
  const summary = summaryQuery.data;
  const current = summary?.current;
  const previous = summary?.previous;
  const teamBreakdown = summary?.team_breakdown || [];
  const totalAgents = Number(current?.total_agents || 0);
  const classCounts = toClassCounts(current?.grade_counts);
  const previousSummaries = previous?.team_breakdown || [];
  const previousTotalAgents = Number(previous?.total_agents || 0);
  const previousClassCounts = toClassCounts(previous?.grade_counts);
  const uniqueMonths = Array.from(
    new Set(
      (catalogQuery.data?.periods || [])
        .slice()
        .sort((left, right) => left.key.localeCompare(right.key))
        .map((period) => period.month),
    ),
  );

  return {
    summaries: teamBreakdown,
    previousSummaries,
    totalAgents,
    uniqueTeamCount: teamBreakdown.length,
    overallAvgScore: Number(current?.average_score || 0),
    pctAB: totalAgents ? ((classCounts.A + classCounts.B) / totalAgents) * 100 : 0,
    pctDE: totalAgents ? ((classCounts.D + classCounts.E) / totalAgents) * 100 : 0,
    allClassCounts: classCounts,
    uniqueMonths,
    activePeriod: summary?.period || activePeriod,
    previousPeriod: summary?.previous_period || null,
    previousTotalAgents,
    previousOverallAvgScore: Number(previous?.average_score || 0),
    previousPctAB: previousTotalAgents ? ((previousClassCounts.A + previousClassCounts.B) / previousTotalAgents) * 100 : 0,
    previousPctDE: previousTotalAgents ? ((previousClassCounts.D + previousClassCounts.E) / previousTotalAgents) * 100 : 0,
    loading: catalogQuery.isLoading || summaryQuery.isLoading,
    dataSource: summary ? 'api' : 'empty',
    errorMessage: summaryQuery.error instanceof Error
      ? summaryQuery.error.message
      : catalogQuery.error instanceof Error
        ? catalogQuery.error.message
        : null,
  };
}
