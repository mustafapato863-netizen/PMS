import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../lib/apiClient';
import type { AgentRecord } from '../../types';
import type { MarketingTeamConfig } from './types';

export const useMarketingData = () => {
  const configQuery = useQuery({
    queryKey: ['marketing-config'],
    queryFn: async () => {
      const response = await apiFetch<{ success: boolean; data: MarketingTeamConfig }>(
        '/api/config/teams/Marketing?performance_level=Employee',
      );
      return response.data;
    },
    staleTime: Infinity,
  });

  const recordsQuery = useQuery({
    queryKey: ['marketing-performance'],
    queryFn: async () => {
      const response = await apiFetch<{ success: boolean; data: AgentRecord[] }>(
        '/api/performance?team=Marketing&performance_level=Employee',
      );
      return response.data;
    },
    staleTime: 2 * 60 * 1000,
  });

  return {
    config: configQuery.data,
    records: recordsQuery.data || [],
    loading: configQuery.isLoading || recordsQuery.isLoading,
    error: configQuery.error || recordsQuery.error,
    refetch: async () => {
      await Promise.all([configQuery.refetch(), recordsQuery.refetch()]);
    },
  };
};
