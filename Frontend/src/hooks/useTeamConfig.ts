/**
 * React Query hooks for team configurations.
 * Provides centralized, cached access to team config data from backend.
 * Configs are fetched once per session and cached indefinitely.
 */

import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/apiClient';
import { validateTeamConfig, validateTeamConfigs, type TeamConfig } from '../schemas/teamConfig.schema';

const MERGED_TEAM_SOURCES: Record<string, string[]> = {
  'Pre-Approvals OP Final': ['Pre-Approvals OP Dubai', 'Pre-Approvals OP Final SHJAJM'],
  'Pre-Approvals IP Final': ['Pre-Approvals IP Final Dubai', 'Pre-Approvals IP Final SHJAJM'],
};

function mergeTeamConfigs(teamName: string, configs: TeamConfig[]): TeamConfig {
  const base = configs[0];
  const positions = Object.fromEntries(configs.flatMap((config) =>
    Object.entries(config.performance_levels?.Employee?.positions || {})
  ));
  const performanceLevels = {
    ...(base.performance_levels || {}),
    Employee: {
      ...(base.performance_levels?.Employee || {}),
      kpis: [],
      positions,
    },
  };
  return validateTeamConfig({
    ...base,
    team: teamName,
    db_name: teamName,
    kpis: [],
    performance_levels: performanceLevels,
  });
}

/**
 * Fetch a single team's configuration
 * @param teamName - Name of the team (e.g., "Inbound", "Sales")
 * @returns Query object with team config or error
 */
export function useTeamConfig(teamName: string) {
  return useQuery({
    queryKey: ['team-config', teamName],
    queryFn: async () => {
      const sources = MERGED_TEAM_SOURCES[teamName];
      if (sources) {
        const sourceConfigs = await Promise.all(sources.map(async (source) => {
          const json = await apiFetch<{ success: boolean; data: unknown; error?: string }>(
            `/api/config/teams/${source}`
          );
          return validateTeamConfig(json.data);
        }));
        return mergeTeamConfigs(teamName, sourceConfigs);
      }
      const json = await apiFetch<{ success: boolean; data: unknown; error?: string }>(
        `/api/config/teams/${teamName}`
      );
      // Validate response matches schema
      return validateTeamConfig(json.data);
    },
    enabled: !!teamName,
    staleTime: Infinity, // Config never changes during a session
    retry: 2,
  });
}

/**
 * Fetch all team configurations at once
 * @returns Query object with array of team configs or error
 */
export function useAllTeamConfigs() {
  return useQuery({
    queryKey: ['team-configs'],
    queryFn: async () => {
      const json = await apiFetch<{ success: boolean; data: unknown; error?: string }>(
        '/api/config/teams'
      );
      // Validate response matches schema
      return validateTeamConfigs(json.data);
    },
    staleTime: Infinity, // Config never changes during a session
    retry: 2,
  });
}

/**
 * Get a team config's KPIs by label
 * Useful for finding specific KPI configuration
 * @param teamName - Name of the team
 * @param kpiLabel - Label of KPI to find (e.g., "Attendance Rate")
 * @returns KPI object or undefined
 */
export function useTeamKPI(teamName: string, kpiLabel: string) {
  const { data: config, ...query } = useTeamConfig(teamName);
  
  return {
    ...query,
    data: config?.kpis.find(k => k.label === kpiLabel),
  };
}

/**
 * Get all KPI keys for a team (useful for knowing which KPIs are available)
 * @param teamName - Name of the team
 * @returns Array of KPI keys or undefined
 */
export function useTeamKPIKeys(teamName: string) {
  const { data: config, ...query } = useTeamConfig(teamName);
  
  return {
    ...query,
    data: config?.kpis.map(k => k.key),
  };
}

/**
 * Get grade thresholds for a specific team
 * @param teamName - Name of the team
 * @returns Grade thresholds object or undefined
 */
export function useTeamGradeThresholds(teamName: string) {
  const { data: config, ...query } = useTeamConfig(teamName);
  
  return {
    ...query,
    data: config?.grade_thresholds,
  };
}
