/**
 * Team Management Hook
 * React Query hooks for team API operations (CRUD).
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { apiFetch } from '../lib/apiClient';

export interface Team {
  id: string;
  name: string;
  display_name: string;
  team_level: 'employee' | 'management';
  region: string;
  description?: string;
  is_active: boolean;
  team_lead?: string;
  team_lead_email?: string;
  kpi_keys?: string[];
  kpi_weights?: Record<string, number>;
}

export interface CreateTeamRequest {
  name: string;
  display_name: string;
  region: string;
  description?: string;
  kpi_keys: string[];
  kpi_weights: Record<string, number>;
  team_lead?: string;
  team_lead_email?: string;
}

interface OnboardingStep {
  step_number: number;
  name: string;
  completed: boolean;
  description?: string;
  error?: string;
}

interface OnboardingStatus {
  status: string;
  progress?: number;
  current_step?: number;
  steps?: OnboardingStep[];
}

/**
 * Fetch all teams
 */
function useTeams() {
  return useQuery({
    queryKey: ['teams'],
    queryFn: async () => {
      const data = await apiFetch<{ teams: Team[]; total: number }>('/api/team-management/teams');
      return data.teams || [];
    },
    staleTime: 2 * 60 * 1000, // 2 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes
  });
}

/**
 * Fetch single team
 */
function useTeam(teamName: string) {
  return useQuery({
    queryKey: ['team', teamName],
    queryFn: () => apiFetch<Team>(`/api/team-management/teams/${teamName}`),
    enabled: !!teamName,
  });
}

/**
 * Create team mutation
 */
function useCreateTeam() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateTeamRequest) =>
      apiFetch<Team>('/api/team-management/teams', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['teams'] });
    },
  });
}

/**
 * Update team mutation
 */
function useUpdateTeam() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ teamName, data }: { teamName: string; data: Partial<CreateTeamRequest> }) =>
      apiFetch<Team>(`/api/team-management/teams/${teamName}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['teams'] });
      queryClient.invalidateQueries({ queryKey: ['team', variables.teamName] });
    },
  });
}

/**
 * Delete team mutation
 */
function useDeleteTeam() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (teamName: string) =>
      apiFetch<{ success: boolean }>(`/api/team-management/teams/${teamName}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['teams'] });
    },
  });
}

/**
 * Validate team mutation
 */
function useValidateTeam() {
  return useMutation({
    mutationFn: (teamName: string) =>
      apiFetch<{ valid: boolean; errors: string[] }>(`/api/team-management/teams/${teamName}/validate`, {
        method: 'POST',
      }),
  });
}

/**
 * Start team onboarding mutation
 */
function useStartOnboarding() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ teamName, autoProceed = true }: { teamName: string; autoProceed?: boolean }) =>
      apiFetch<{ success: boolean }>(`/api/team-management/teams/${teamName}/onboard`, {
        method: 'POST',
        body: JSON.stringify({
          team_name: teamName,
          auto_proceed: autoProceed,
          send_notifications: true,
        }),
      }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['team', variables.teamName] });
    },
  });
}

/**
 * Get team onboarding status query
 */
function useOnboardingStatus(teamName: string) {
  return useQuery({
    queryKey: ['onboarding-status', teamName],
    queryFn: () => apiFetch<OnboardingStatus>(`/api/team-management/teams/${teamName}/onboarding-status`),
    enabled: !!teamName,
    refetchInterval: 2000, // Poll every 2 seconds during onboarding
  });
}

/**
 * Composite hook for team management
 */
export function useTeamManagement() {
  const [error, setError] = useState<string | null>(null);

  const teamsQuery = useTeams();
  const createMutation = useCreateTeam();
  const updateMutation = useUpdateTeam();
  const deleteMutation = useDeleteTeam();
  const onboardMutation = useStartOnboarding();

  const createTeam = async (data: CreateTeamRequest) => {
    try {
      setError(null);
      await createMutation.mutateAsync(data);
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create team';
      setError(message);
      return false;
    }
  };

  const updateTeam = async (teamName: string, data: Partial<CreateTeamRequest>) => {
    try {
      setError(null);
      await updateMutation.mutateAsync({ teamName, data });
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update team';
      setError(message);
      return false;
    }
  };

  const deleteTeam = async (teamName: string) => {
    try {
      setError(null);
      await deleteMutation.mutateAsync(teamName);
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete team';
      setError(message);
      return false;
    }
  };

  const startOnboarding = async (teamName: string, autoProceed = true) => {
    try {
      setError(null);
      await onboardMutation.mutateAsync({ teamName, autoProceed });
      return true;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to start onboarding';
      setError(message);
      return false;
    }
  };

  const refreshTeams = () => {
    teamsQuery.refetch();
  };

  return {
    teams: teamsQuery.data || [],
    isLoading: teamsQuery.isLoading || teamsQuery.isFetching,
    error,
    createTeam,
    updateTeam,
    deleteTeam,
    startOnboarding,
    refreshTeams,
  };
}

export { useTeams, useTeam, useCreateTeam, useUpdateTeam, useDeleteTeam, useValidateTeam, useStartOnboarding, useOnboardingStatus };
