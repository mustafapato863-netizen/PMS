import { describe, expect, it } from 'vitest';
import {
  prepareBalancedScorecardTeamParams,
  resolveBalancedScorecardView,
} from './balancedScorecardNavigation';

describe('resolveBalancedScorecardView', () => {
  it('opens managerial navigation in the management overview', () => {
    expect(resolveBalancedScorecardView(null, 'Managerial')).toBe('perspective_summary');
  });

  it('opens corporate navigation in the strategic overview', () => {
    expect(resolveBalancedScorecardView(null, 'Corporate')).toBe('strategy_map');
  });

  it('preserves an explicit view selection', () => {
    expect(resolveBalancedScorecardView('strategy_map', 'Managerial')).toBe('strategy_map');
    expect(resolveBalancedScorecardView('perspective_summary', 'Corporate')).toBe('perspective_summary');
  });
});

describe('prepareBalancedScorecardTeamParams', () => {
  it('keeps period filters while clearing team-specific managerial filters', () => {
    const result = prepareBalancedScorecardTeamParams(
      new URLSearchParams(
        'month=June&year=2026&employee_ids=SGHD70136&perspective=Financial&kpi=revenue&bsc_view=strategy_map',
      ),
      'Managerial',
    );

    expect(result.get('month')).toBe('June');
    expect(result.get('year')).toBe('2026');
    expect(result.get('performance_level')).toBe('Managerial');
    expect(result.get('bsc_view')).toBe('perspective_summary');
    expect(result.has('employee_ids')).toBe(false);
    expect(result.has('perspective')).toBe(false);
    expect(result.has('kpi')).toBe(false);
  });
});
