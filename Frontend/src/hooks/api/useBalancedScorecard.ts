import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../lib/apiClient';

export interface BalancedScorecardResponse {
  team?: {
    id?: string;
    name?: string;
    performance_level?: string;
    team_level?: 'management';
    top_position?: string | null;
  };
  scorecard?: {
    score?: number | null;
    target_score?: number | null;
    status?: string;
    state?: string;
    coverage?: number | null;
  };
  selection?: {
    month?: string | null;
    year?: number | null;
    employee_ids?: string[];
    people_count?: number;
    history_months?: number;
    data_source?: string;
  };
  available_periods?: Array<{
    month: string;
    year: number;
  }>;
  available_people?: Array<{
    employee_id: string;
    employee_name: string;
    team_name?: string;
    role?: string;
    position?: string;
  }>;
  contributors?: Array<{
    employee_id: string;
    employee_name: string;
    overall_score?: number | null;
    role?: string;
    position?: string;
    perspectives?: Record<string, {
      score?: number | null;
      weighted_contribution?: number | null;
      measured_weight?: number | null;
      top_kpi_label?: string;
      trend?: number | null;
    }>;
  }>;
  perspectives?: Array<{
    key: string;
    label: string;
    focus?: string;
    display_order?: number;
    score?: number | null;
    status?: string;
    state?: string;
    weighted_contribution?: number | null;
    configured_weight?: number | null;
    measured_weight?: number | null;
    coverage?: number | null;
    trend_vs_previous?: number | null;
    target_score?: number | null;
    primary_driver?: {
      kpi_label?: string;
    } | null;
  }>;
  kpi_table?: Array<{
    kpi_key: string;
    kpi_label: string;
    perspective: string;
    score?: number | null;
    status?: string;
    state?: string;
    weight?: number;
    measured_weight?: number | null;
    direction?: 'higher_better' | 'lower_better';
    actual_value?: number | null;
    target_value?: number | null;
    weighted_contribution?: number | null;
    performance_gap?: number | null;
    record_count?: number;
    unit?: string;
  }>;
  history?: Array<{
    month: string;
    year: number;
    score?: number | null;
    perspective_scores?: Record<string, number | null>;
  }>;
  selected_kpi?: {
    key: string;
    label: string;
    current?: {
      kpi_key: string;
      kpi_label: string;
      perspective: string;
      score?: number | null;
      actual_value?: number | null;
      target_value?: number | null;
      direction?: 'higher_better' | 'lower_better';
    } | null;
    history?: Array<{
      month: string;
      year: number;
      kpi_key: string;
      kpi_label: string;
      perspective: string;
      score?: number | null;
      actual_value?: number | null;
      target_value?: number | null;
      direction?: 'higher_better' | 'lower_better';
    }>;
  } | null;
}

export type BscPerson = NonNullable<BalancedScorecardResponse['available_people']>[number];
export type BscContributor = NonNullable<BalancedScorecardResponse['contributors']>[number];
export type BscKpiRow = NonNullable<BalancedScorecardResponse['kpi_table']>[number];
export type BscPerspective = NonNullable<BalancedScorecardResponse['perspectives']>[number];
export type BscHistoryPoint = NonNullable<BalancedScorecardResponse['history']>[number];

export function useBalancedScorecard(params: {
  team: string | null;
  performanceLevel: 'Managerial' | 'Corporate';
  month: string;
  year: string | null;
  employeeIds: string[];
  selectedKpi?: string | null;
  branch?: string;
  view?: string;
  enabled?: boolean;
}) {
  return useQuery({
    queryKey: [
      'balanced-scorecard',
      params.team,
      params.performanceLevel,
      params.month,
      params.year,
      params.employeeIds.join(','),
      params.selectedKpi,
      params.branch,
      params.view,
    ],
    queryFn: async (): Promise<BalancedScorecardResponse> => {
      const search = new URLSearchParams();
      if (params.team) search.set('team', params.team);
      search.set('performance_level', params.performanceLevel);
      if (params.month && params.month !== 'All') search.set('month', params.month);
      if (params.year) search.set('year', params.year);
      // All Months needs the full selected-year history instead of the
      // default latest-six-period window.
      search.set('history_months', params.month === 'All' ? '24' : '6');
      params.employeeIds.forEach((id) => search.append('employee_ids', id));
      if (params.selectedKpi) search.set('selected_kpi', params.selectedKpi);
      if (params.branch && params.branch !== 'all') search.set('branch', params.branch);
      if (params.view) search.set('view', params.view);

      const json = await apiFetch<{ success: boolean; data: BalancedScorecardResponse }>(
        `/api/performance/balanced-scorecard?${search.toString()}`,
      );
      return json.data;
    },
    enabled: params.enabled ?? (!!params.team && !!params.performanceLevel),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
}
