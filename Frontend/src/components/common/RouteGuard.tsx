import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useUserRole } from '../../context/RoleContext';
import { canAccessRoute } from '../../lib/access';

export interface RouteGuardProps {
  children: ReactNode;
  /** Stored role strings allowed on this route (e.g. `['Admin', 'General Manager']`). */
  allowedRoles: readonly string[];
  redirectTo?: string;
}

export default function RouteGuard({ children, allowedRoles, redirectTo = '/executive' }: RouteGuardProps) {
  const { role } = useUserRole();
  if (!canAccessRoute({ role, allowedRoles })) {
    return <Navigate to={redirectTo} replace />;
  }
  return <>{children}</>;
}
