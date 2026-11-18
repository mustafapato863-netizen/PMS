/** Tier-aware AI access gate. Mirrors the backend `require_ai_access` dependency. */

import type { AiAccessTier } from '../types';

export const DEFAULT_AI_TIER: AiAccessTier = 'admin_only';

/** Roles allowed in the managers_and_admins tier. */
const MANAGER_TIER_ROLES = new Set(['Admin', 'General Manager', 'Manager', 'Executive']);

export function hasAiAccess(role: string | null | undefined, aiTier?: AiAccessTier): boolean {
  const tier = aiTier ?? DEFAULT_AI_TIER;
  if (!role) return false;
  if (tier === 'admin_only') return role === 'Admin';
  if (tier === 'managers_and_admins') return MANAGER_TIER_ROLES.has(role);
  // all_authenticated_users → any role with a valid session passes
  return true;
}

/** Map a role to its persona tier label for UI display. */
export function personaLabel(role: string | null | undefined, isSelfOnly?: boolean): string {
  if (role === 'Admin' || role === 'General Manager') return 'Global';
  if (role === 'Executive') return 'Executive';
  if (isSelfOnly || role === 'Agent' || role === 'Employee') return 'My 360°';
  return 'Manager';
}
