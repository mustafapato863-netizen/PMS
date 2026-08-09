/**
 * KPI Weights Hook
 * Fetches KPI weight configurations for teams.
 * Replaces manual fetch() calls in useEffect with React Query caching.
 */

import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../lib/apiClient';
import { sameCanonicalTeam } from '../../types';

export interface KPIWeightConfig {
  team: string;
  weights: Record<string, number>;
}

export function normalizeTeamName(teamName: string) {
  return teamName.trim().toLowerCase().replace(/[^a-z0-9]/g, '');
}

export function matchesTeamConfig(config: KPIWeightConfig, teamName: string) {
  const target = normalizeTeamName(teamName);
  return [config.team].filter(Boolean).some((value) =>
    normalizeTeamName(String(value)) === target || sameCanonicalTeam(String(value), teamName)
  );
}

/**
 * Fetch KPI weights for all teams
 * @param userRole - User role for authorization (legacy parameter)
 * @returns Query object with KPI weights for all teams
 */
export function useAllKpiWeights(_userRole?: string) {
  void _userRole;
  return useQuery({
    queryKey: ['kpi-weights'],
    queryFn: async () => {
      const json = await apiFetch<{ success: boolean; data: KPIWeightConfig[]; error?: string }>(
        '/api/settings/weights'
      );
      return json.data;
    },
    staleTime: 30 * 60 * 1000, // 30 minutes (weights rarely change)
    retry: 2,
  });
}

/**
 * Fetch KPI weights for a specific team
 * @param teamName - Name of the team
 * @param userRole - User role for authorization
 * @returns Query object with weights or undefined if team not found
 */
export function useTeamKpiWeights(teamName: string, userRole?: string) {
  const { data: allWeights, ...query } = useAllKpiWeights(userRole);

  return {
    ...query,
    data: allWeights?.find((w) => matchesTeamConfig(w, teamName))?.weights,
  };
}

/**
 * Get all weights for a specific KPI across teams
 * Useful for comparing a KPI weight across different teams
 * @param kpiKey - Key of the KPI (e.g., "Attend", "Booking")
 * @param userRole - User role for authorization
 * @returns Query object with weights by team
 */
export function useKpiWeightByTeams(kpiKey: string, userRole?: string) {
  const { data: allWeights, ...query } = useAllKpiWeights(userRole);

  return {
    ...query,
    data: allWeights?.reduce(
      (acc, config) => {
        if (config.weights[kpiKey]) {
          acc[config.team] = config.weights[kpiKey];
        }
        return acc;
      },
      {} as Record<string, number>
    ),
  };
}
