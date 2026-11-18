/** Tier-aware route guard for the AI workspace. Backend `require_ai_access` is the source of truth. */

import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../../context/auth';
import { hasAiAccess } from '../../utils/aiAccess';

export function AiRouteGuard({ children, redirectTo = '/executive' }: { children: ReactNode; redirectTo?: string }) {
  const { currentUser } = useAuth();
  const role = currentUser?.role;
  if (!hasAiAccess(role, currentUser?.ai_access_tier)) {
    return <Navigate to={redirectTo} replace />;
  }
  return <>{children}</>;
}
