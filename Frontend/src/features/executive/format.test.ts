import { describe, expect, it } from 'vitest';
import { directionAdjustedDelta, kpiChangeDelta, kpiGapDelta, kpiMovementTone, normalizeKpiDirection } from './format';

describe('direction-aware Executive KPI deltas', () => {
  it('normalizes only directions supplied by the KPI', () => {
    expect(normalizeKpiDirection('lower_better')).toBe('lower_better');
    expect(normalizeKpiDirection('higher_better')).toBe('higher_better');
    expect(normalizeKpiDirection(null)).toBeNull();
    expect(normalizeKpiDirection('unknown')).toBeNull();
  });

  it('makes positive mean better for either KPI direction', () => {
    expect(directionAdjustedDelta(4, 'higher_better')).toBe(4);
    expect(directionAdjustedDelta(4, 'lower_better')).toBe(-4);
    expect(directionAdjustedDelta(-4, 'lower_better')).toBe(4);
  });

  it('uses normalized API values and direction-aware raw fallbacks for gaps and changes', () => {
    expect(kpiGapDelta({ gap_value: null, raw_gap: 4, kpi_direction: 'lower_better' })).toBe(-4);
    expect(kpiGapDelta({ gap_value: 3, raw_gap: -3, kpi_direction: 'higher_better' })).toBe(3);
    expect(kpiChangeDelta({ change_value: null, raw_change: 2, kpi_direction: 'lower_better' })).toBe(-2);
    expect(kpiChangeDelta({ change_value: null, raw_change: 2, kpi_direction: null })).toBeNull();
  });

  it('keeps an unknown direction neutral instead of assuming higher-is-better', () => {
    expect(kpiMovementTone({ trend_status: null, change_value: null, raw_change: 2, kpi_direction: null })).toBe('neutral');
    expect(kpiMovementTone({ trend_status: null, change_value: null, raw_change: 2, kpi_direction: 'lower_better' })).toBe('bad');
    expect(kpiMovementTone({ trend_status: null, change_value: null, raw_change: -2, kpi_direction: 'lower_better' })).toBe('good');
  });
});
