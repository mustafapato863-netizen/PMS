import { describe, expect, it } from 'vitest';
import { compareScoringBasis, type BasisRecord } from './scoringBasisComparison';

function kpi(overrides: Record<string, unknown> = {}) {
  return {
    kpi_key: 'Attendance',
    target_value: 0.65,
    weight_applied: 0.7,
    direction: 'higher_better',
    unit: '%',
    actual_value: 0.6,
    evaluation_pinned: true,
    ...overrides,
  };
}

function record(employee: string, month: string, kpis = [kpi()], team = 'Outbound'): BasisRecord {
  return {
    employee_id: employee,
    team,
    position: 'Agent',
    performance_level: 'Employee',
    year: 2026,
    month,
    kpi_values: kpis,
  };
}

describe('compareScoringBasis', () => {
  it('warns when the target changes and the same person actual is unchanged', () => {
    const result = compareScoringBasis(
      [record('A', 'August', [kpi({ target_value: 0.65, weight_applied: 0.6, actual_value: 0.6 })])],
      [record('A', 'July', [kpi({ target_value: 0.55, weight_applied: 0.7, actual_value: 0.6 })])],
    );
    expect(result.state).toBe('changed');
    expect(result.like_for_like).toBe(false);
    expect(result.raw_performance).toBe('unchanged');
    expect(result.message).toContain('Scores can be affected by evaluation settings.');
    expect(result.message).toContain('Comparable raw performance is unchanged.');
    expect(result.message?.toLowerCase()).not.toContain('caused');
  });

  it('does not warn when only the matched actual changes', () => {
    const result = compareScoringBasis(
      [record('A', 'August', [kpi({ actual_value: 0.4 })])],
      [record('A', 'July', [kpi({ actual_value: 0.6 })])],
    );
    expect(result.state).toBe('unchanged');
    expect(result.like_for_like).toBe(true);
    expect(result.raw_performance).toBe('changed');
    expect(result.message).toBeNull();
  });

  it('does not treat a different employee actual as that person changing', () => {
    const result = compareScoringBasis(
      [record('B', 'August', [kpi({ actual_value: 0.4 })])],
      [record('A', 'July', [kpi({ actual_value: 0.6 })])],
    );
    expect(result.state).toBe('unchanged');
    expect(result.like_for_like).toBe(false);
    expect(result.raw_performance).toBe('unknown');
    expect(result.reasons).toEqual([]);
    expect(result.message?.toLowerCase()).toContain('population changed');
  });

  it('keeps an added KPI from claiming all raw performance is unchanged', () => {
    const result = compareScoringBasis(
      [record('A', 'August', [kpi({ actual_value: 0.6 }), kpi({ kpi_key: 'Productivity', target_value: 10, weight_applied: 0.1, actual_value: 8, unit: 'count' })])],
      [record('A', 'July', [kpi({ actual_value: 0.6 })])],
    );
    expect(result.state).toBe('changed');
    expect(result.reasons).toEqual(['kpi_set']);
    expect(result.raw_performance).toBe('partial');
    expect(result.message).toContain('Shared comparable KPI values are unchanged.');
    expect(result.message).not.toContain('Comparable raw performance is unchanged.');
    expect(JSON.stringify(result)).not.toContain('Productivity');
  });

  it('treats a one-sided formula as unknown and identical rules as unchanged', () => {
    const oneSided = compareScoringBasis(
      [record('A', 'August')],
      [record('A', 'July', [kpi({ formula: 'target_ratio' })])],
    );
    const same = compareScoringBasis(
      [record('A', 'August', [kpi({ formula: 'target_ratio' })], )],
      [record('A', 'July', [kpi({ formula: 'target_ratio' })])],
    );
    expect(oneSided.state).toBe('unknown');
    expect(oneSided.like_for_like).toBe(false);
    expect(oneSided.message?.toLowerCase()).not.toContain('unchanged');
    expect(same.state).toBe('unchanged');
    expect(same.like_for_like).toBe(true);
  });

  it('does not default an invalid direction or accept a non-finite target', () => {
    const direction = compareScoringBasis(
      [record('A', 'August', [kpi({ direction: 'sideways' })])],
      [record('A', 'July')],
    );
    const target = compareScoringBasis(
      [record('A', 'August', [kpi({ target_value: Number.NaN })])],
      [record('A', 'July', [kpi({ target_value: Number.POSITIVE_INFINITY })])],
    );
    expect(direction.state).toBe('unknown');
    expect(direction.like_for_like).toBe(false);
    expect(target.state).toBe('unknown');
    expect(target.like_for_like).toBe(false);
  });

  it('does not treat an added team as a like-for-like population', () => {
    const result = compareScoringBasis(
      [record('A', 'August'), record('B', 'August', [kpi()], 'Inbound')],
      [record('A', 'July')],
    );
    expect(result.like_for_like).toBe(false);
    expect(result.raw_performance).not.toBe('unchanged');
    expect(result.raw_performance).not.toBe('changed');
    expect(result.message).toBeTruthy();
    expect(result.message).not.toContain('Comparable raw performance is unchanged.');
  });

  it('treats a blank position as a canonical team scope and keeps it distinct', () => {
    const blank = (employee: string, month: string): BasisRecord => ({
      ...record(employee, month),
      team: 'Coding',
      position: '',
      performance_level: 'Employee',
    });
    const matched = compareScoringBasis([blank('A', 'August')], [blank('A', 'July')]);
    const separated = compareScoringBasis(
      [blank('A', 'August')],
      [{ ...blank('A', 'July'), position: 'Agent' }],
    );
    expect(matched.state).toBe('unchanged');
    expect(matched.like_for_like).toBe(true);
    expect(separated.like_for_like).toBe(false);
  });

  it('does not drop an extra row that has no team or level', () => {
    const result = compareScoringBasis(
      [
        { ...record('A', 'August'), team: 'Coding', position: 'Agent', performance_level: 'Employee' },
        { ...record('B', 'August'), team: '', position: 'Agent', performance_level: '' },
      ],
      [{ ...record('A', 'July'), team: 'Coding', position: 'Agent', performance_level: 'Employee' }],
    );
    expect(result.like_for_like).toBe(false);
    expect(result.raw_performance).not.toBe('unchanged');
  });

  it('does not trust a blank team, position, and level as one shared scope', () => {
    const blank = (employee: string, month: string): BasisRecord => ({
      ...record(employee, month),
      team: '',
      position: '',
      performance_level: '',
    });
    const result = compareScoringBasis([blank('A', 'August')], [blank('A', 'July')]);
    expect(result.like_for_like).toBe(false);
    expect(['unknown', 'unavailable']).toContain(result.state);
  });

  it('does not treat an explicit source change as comparable raw evidence', () => {
    const result = compareScoringBasis(
      [record('A', 'August', [kpi({ source: 'system_b' })])],
      [record('A', 'July', [kpi({ source: 'system_a' })])],
    );
    expect(result.state).toBe('changed');
    expect(result.raw_performance).not.toBe('unchanged');
    expect(result.raw_performance).not.toBe('changed');
    expect(result.message ?? '').not.toContain('Comparable raw performance is unchanged.');
  });

  it('canonicalizes scientific notation and negative zero without rescaling percents', () => {
    const tiny = compareScoringBasis(
      [record('A', 'August', [kpi({ target_value: 1e-7, actual_value: 1e-7 })])],
      [record('A', 'July', [kpi({ target_value: '0.0000001', actual_value: '0.0000001' })])],
    );
    const large = compareScoringBasis(
      [record('A', 'August', [kpi({ target_value: 1e21, actual_value: 1e21 })])],
      [record('A', 'July', [kpi({ target_value: '1e+21', actual_value: '1000000000000000000000' })])],
    );
    const negativeZero = compareScoringBasis(
      [record('A', 'August', [kpi({ target_value: -0, actual_value: '-0.0' })])],
      [record('A', 'July', [kpi({ target_value: 0, actual_value: '0' })])],
    );
    const scale = compareScoringBasis(
      [record('A', 'August', [kpi({ target_value: 0.65 })])],
      [record('A', 'July', [kpi({ target_value: 65 })])],
    );
    expect(tiny.state).toBe('unchanged');
    expect(tiny.like_for_like).toBe(true);
    expect(large.state).toBe('unchanged');
    expect(large.like_for_like).toBe(true);
    expect(negativeZero.state).toBe('unchanged');
    expect(negativeZero.like_for_like).toBe(true);
    expect(scale.state).toBe('changed');
    expect(scale.reasons).toEqual(['target']);
  });

  it('does not treat delimiter-shaped source values as the same source tuple', () => {
    const result = compareScoringBasis(
      [record('A', 'August', [kpi({ source: 'a|target_source=b' })])],
      [record('A', 'July', [kpi({ source: 'a', target_source: 'b' })])],
    );
    expect(result.state).toBe('changed');
    expect(result.reasons).toContain('source');
  });

  it('does not mutate the records it groups', () => {
    const current = [record('A', 'August'), record('B', 'August')];
    const previous = [record('A', 'July'), record('B', 'July')];
    const snapshot = JSON.stringify([current, previous]);
    compareScoringBasis(current, previous);
    expect(JSON.stringify([current, previous])).toBe(snapshot);
    expect(current).toHaveLength(2);
    expect(previous).toHaveLength(2);
  });
});
