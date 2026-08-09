import type { ViewKey } from '../balanced-scorecard/types';

export function resolveBalancedScorecardView(
  requestedView: string | null,
  performanceLevel: string,
): ViewKey {
  if (requestedView === 'strategy_map' || requestedView === 'perspective_summary') {
    return requestedView;
  }
  return performanceLevel === 'Corporate' ? 'strategy_map' : 'perspective_summary';
}

export function prepareBalancedScorecardTeamParams(
  current: URLSearchParams,
  performanceLevel: 'Managerial' | 'Corporate',
): URLSearchParams {
  const next = new URLSearchParams(current);
  next.set('performance_level', performanceLevel);
  next.set('bsc_view', performanceLevel === 'Corporate' ? 'strategy_map' : 'perspective_summary');
  next.delete('employee_ids');
  next.delete('perspective');
  next.delete('kpi');
  return next;
}
