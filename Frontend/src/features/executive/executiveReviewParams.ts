import type { ExecutiveScope } from './types';

export const REVIEW_PREFIX = 'review_';

export function executiveReviewParams(
  current: URLSearchParams,
  scope: Pick<ExecutiveScope, 'region' | 'branch' | 'performance_level'>,
  selection: { fn: string; period: string; team?: string; region?: string; role?: string },
): URLSearchParams {
  const next = new URLSearchParams(current);
  next.set('review_deepDive', selection.fn);
  next.set('review_period', selection.period);
  next.set('review_region', scope.region || 'all');
  const optional = {
    branch: scope.branch,
    level: scope.performance_level,
    team: selection.role ? undefined : selection.team,
    role: selection.role,
    teamRegion: selection.region,
  };
  for (const [key, value] of Object.entries(optional)) {
    if (value) next.set(REVIEW_PREFIX + key, value);
    else next.delete(REVIEW_PREFIX + key);
  }
  next.delete('review_employee');
  return next;
}
