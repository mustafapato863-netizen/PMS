import { useMemo } from 'react';
import { useAuth } from '../../context/auth';
import { useUserRole } from '../../context/RoleContext';
import { isFunctionViewerRole, readAccessibleFunctions } from '../../lib/access';
import { allowedFunctionsFor, isTeamInFunctions } from './functions';
import type { ExecutiveFunction } from './types';

export interface FunctionScope {
  /** True only for Function Viewer; every other role keeps its existing scoping. */
  restricted: boolean;
  allowed: ExecutiveFunction[];
  allowsTeam: (team: string | null | undefined) => boolean;
}

/** Function Viewer scope from /auth/me `accessible_functions` (all four when absent). */
export function useFunctionScope(): FunctionScope {
  const { role } = useUserRole();
  const { currentUser } = useAuth();
  return useMemo(() => {
    const restricted = isFunctionViewerRole(role);
    const allowed = allowedFunctionsFor(role, readAccessibleFunctions(currentUser));
    return {
      restricted,
      allowed,
      allowsTeam: (team) => !restricted || isTeamInFunctions(team, allowed),
    };
  }, [currentUser, role]);
}
