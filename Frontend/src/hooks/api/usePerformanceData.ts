/**
 * Performance Data Hook
 * Fetches team performance data with automatic caching and error handling.
 * Replaces manual useTeamData hook fetch logic with React Query.
 */

import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../lib/apiClient';
import type { PerformanceLevelFilter } from '../../types';

export interface PerformanceData {
  team: string;
  month: string;
  employees: Array<{
    id: string;
    name: string;
    score: number;
    grade: string;
    status: string;
  }>;
}

/**
 * Fetch performance data for a specific team and month
 * @param team - Team name (optional, filters for specific team)
 * @param month - Month to fetch data for (default: "All")
 * @param userRole - User role for authorization (legacy parameter)
 * @returns Query object with performance data
 */
export function usePerformanceData(
  team: string | null = null,
  month: string = 'All',
  _userRole?: string,
  performanceLevel: PerformanceLevelFilter = 'All',
) {
  return useQuery({
    queryKey: ['performance', team, month, performanceLevel],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (month && month !== 'All') params.append('month', month);
      if (team) params.append('team', team);
      if (performanceLevel !== 'All') params.append('performance_level', performanceLevel);

      const queryString = params.toString();
      const endpoint = `/api/performance${queryString ? `?${queryString}` : ''}`;

      const json = await apiFetch<{ success: boolean; data: PerformanceData; error?: string }>(endpoint);
      return json.data;
    },
    staleTime: 10 * 60 * 1000, // 10 minutes
    retry: 2,
  });
}

/**
 * Fetch performance data for all teams in a given month
 * @param month - Month to fetch data for
 * @param userRole - User role for authorization
 * @returns Query object with performance data for all teams
 */
export function useAllTeamsPerformance(month: string = 'All', userRole?: string) {
  return usePerformanceData(null, month, userRole);
}

/**
 * Fetch performance data for a specific team across all months
 * @param team - Team name
 * @param userRole - User role for authorization
 * @returns Query object with performance data
 */
export function useTeamPerformance(team: string, userRole?: string) {
  return usePerformanceData(team, 'All', userRole);
}
