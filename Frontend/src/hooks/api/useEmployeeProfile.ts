/**
 * Employee Profile Hook
 * Fetches complete employee profile including performance history and corrective actions.
 * Replaces manual fetch() calls with React Query caching and error handling.
 */

import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../lib/apiClient';

export interface PerformanceHistoryRecord {
  month: string;
  evaluation: {
    score: number;
    grade: string;
  };
  achievement?: Record<string, number>;
  actual?: Record<string, number>;
}

export interface CorrectiveAction {
  id?: string;
  manager_action: string;
  manager_notes?: string;
  timestamp?: string;
  month?: string;
}

export interface EmployeeProfile {
  employee: {
    id: string;
    name: string;
    team: string;
    status: string;
  };
  performance_history: PerformanceHistoryRecord[];
  corrective_action_history: CorrectiveAction[];
}

/**
 * Fetch complete employee profile
 * @param employeeId - ID of the employee to fetch
 * @param userRole - User role for authorization header (legacy parameter)
 * @returns Query object with employee profile data
 */
export function useEmployeeProfile(employeeId: string, _userRole?: string) {
  void _userRole;
  return useQuery({
    queryKey: ['employee', employeeId],
    queryFn: async () => {
      const json = await apiFetch<{ success: boolean; data: EmployeeProfile; error?: string }>(
        `/api/employee/${employeeId}/`
      );
      return json.data;
    },
    enabled: !!employeeId,
    staleTime: 60 * 1000, // 1 minute
    retry: 2,
  });
}

/**
 * Fetch just performance history for an employee
 * Useful when you only need history without full profile
 * @param employeeId - ID of the employee
 * @param userRole - User role for authorization header
 * @returns Query object with performance history
 */
export function useEmployeePerformanceHistory(employeeId: string, userRole?: string) {
  const { data: profile, ...query } = useEmployeeProfile(employeeId, userRole);
  return {
    ...query,
    data: profile?.performance_history,
  };
}

/**
 * Fetch just corrective actions for an employee
 * Useful when you only need actions without full profile
 * @param employeeId - ID of the employee
 * @param userRole - User role for authorization header
 * @returns Query object with corrective actions
 */
export function useEmployeeCorrectiveActions(employeeId: string, userRole?: string) {
  const { data: profile, ...query } = useEmployeeProfile(employeeId, userRole);
  return {
    ...query,
    data: profile?.corrective_action_history,
  };
}
