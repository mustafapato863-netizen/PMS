import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../context/auth';
import { useUserRole } from '../../context/RoleContext';
import { isFunctionViewerRole, readAccessibleFunctions } from '../../lib/access';
import type { ExecutiveFunction } from './types';

type FunctionScopeResolvers = Pick<typeof import('./functions'), 'allowedFunctionsFor' | 'isTeamInFunctions'>;
const NO_FUNCTIONS: ExecutiveFunction[] = [];

export interface FunctionScope {
  /** True only for Function Viewer; every other role keeps its existing scoping. */
  restricted: boolean;
  /** False while Function Viewer-only membership rules are being loaded. */
  ready: boolean;
  /** Access stays denied if the Function Viewer scope module cannot be loaded. */
  loadError: boolean;
  allowed: ExecutiveFunction[];
  allowsTeam: (team: string | null | undefined) => boolean;
}

/** Function Viewer scope from /auth/me `accessible_functions` (none when absent). */
export function useFunctionScope(): FunctionScope {
  const { role } = useUserRole();
  const { currentUser } = useAuth();
  const restricted = isFunctionViewerRole(role);
  const [resolvers, setResolvers] = useState<FunctionScopeResolvers | null>(null);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    if (!restricted) return;

    let active = true;
    void import('./functions')
      .then(({ allowedFunctionsFor, isTeamInFunctions }) => {
        if (active) {
          setResolvers(() => ({ allowedFunctionsFor, isTeamInFunctions }));
          setLoadError(false);
        }
      })
      .catch(() => {
        if (active) setLoadError(true);
      });

    return () => {
      active = false;
    };
  }, [restricted]);

  const allowed = useMemo(() => {
    if (!restricted || !resolvers) return NO_FUNCTIONS;
    return resolvers.allowedFunctionsFor(role, readAccessibleFunctions(currentUser));
  }, [currentUser, resolvers, restricted, role]);

  return {
    restricted,
    ready: !restricted || resolvers !== null || loadError,
    loadError: restricted && loadError,
    allowed,
    allowsTeam: (team) => !restricted || Boolean(resolvers?.isTeamInFunctions(team, allowed)),
  };
}
