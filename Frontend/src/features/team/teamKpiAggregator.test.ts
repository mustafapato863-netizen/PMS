import { describe, expect, it } from 'vitest';
import { validateTeamConfig, type TeamConfig } from '../../schemas/teamConfig.schema';
import type { AgentRecord } from '../../types';
import { aggregateConfiguredTeamKpis, calculateAggregatedTeamPerformance } from './teamKpiAggregator';

const config = (
  aggregation: TeamConfig['kpis'][number]['aggregation'],
): TeamConfig => validateTeamConfig({
  team: 'Config Team',
  db_name: 'Config Team',
  region: 'UAE',
  employee_id_col: 'EmployeeID',
  employee_name_col: 'EmployeeName',
  grade_thresholds: { A: 95, B: 85, C: 75, D: 65 },
  kpis: [{
    key: 'rate',
    label: 'Configured Rate',
    weight: 1,
    direction: 'higher_better',
    unit: '%',
    color: '#10B981',
    actual_col: 'Actual',
    target_col: 'Target',
    aggregation,
  }],
});

const record = (
  id: string,
  actual: number,
  target: number,
  rawData: Record<string, string>,
  weightApplied: number | undefined = 1,
): AgentRecord => ({
  identity: { name: `Agent ${id}`, employee_id: id, team: 'Config Team', month: 'June' },
  calls: { inbound: 0, outbound: 0, total_handled: 0, abandoned: 0, aht_raw: '00:00:00' },
  geo: {
    bookings: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
    attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
  },
  actual: { booking_rate: 0, attend_rate: 0, abandon_rate: 0 },
  achievement: { booking_ach: 0, attend_ach: 0 },
  evaluation: { score: 0, grade: 'E' },
  raw_data: rawData,
  kpi_values: [{
    kpi_key: 'rate',
    label: 'Configured Rate',
    unit: '%',
    direction: 'higher_better',
    actual_value: actual,
    target_value: target,
    achievement_ratio: target > 0 ? actual / target : 0,
    weight_applied: weightApplied as number,
    contribution: actual,
  }],
});

describe('aggregateConfiguredTeamKpis', () => {
  it('pools ratio counters instead of averaging employee percentages', () => {
    const result = aggregateConfiguredTeamKpis([
      record('1', 0.5, 0.9, { numerator: '1', denominator: '2' }),
      record('2', 1, 0.9, { numerator: '9', denominator: '9' }),
    ], config({ method: 'ratio', numerator_col: 'numerator', denominator_col: 'denominator' }));

    expect(result.get('configuredrate')?.actual).toBeCloseTo(10 / 11);
    expect(result.get('configuredrate')?.actual).not.toBeCloseTo(0.75);
  });

  it('accepts the corrected ErrorsClaims spelling used by newer uploads', () => {
    const result = aggregateConfiguredTeamKpis([
      record('1', 0.587, 0.03, { ErrorsClaims: '3', SubmittedClaims: '501' }),
    ], config({ method: 'ratio', numerator_col: 'ErrosClaims', denominator_col: 'SubmittedClaims' }));

    expect(result.get('configuredrate')?.actual).toBeCloseTo(3 / 501);
  });

  it('uses configured source percentages when ratio counters are absent', () => {
    const result = aggregateConfiguredTeamKpis([
      record('1', 0.587, 0.03, { Actual: '0.006', Target: '0.03' }),
    ], config({ method: 'ratio', numerator_col: 'missing_numerator', denominator_col: 'missing_denominator' }));

    expect(result.get('configuredrate')?.actual).toBeCloseTo(0.006);
    expect(result.get('configuredrate')?.target).toBeCloseTo(0.03);
  });

  it('falls back to the employee average when the configured raw counters are unavailable', () => {
    const result = aggregateConfiguredTeamKpis([
      record('1', 0.5, 0.9, {}),
      record('2', 0.7, 0.9, {}),
    ], config({ method: 'ratio', numerator_col: 'numerator', denominator_col: 'denominator' }));

    expect(result.get('configuredrate')?.actual).toBeCloseTo(0.6);
  });

  it('uses the canonical team definition when a KPI record has no stored weight', () => {
    const result = aggregateConfiguredTeamKpis([
      record('1', 0.8, 0.9, {}, undefined),
    ], config({ method: 'average' }));

    expect(result.get('configuredrate')?.weight).toBe(1);
  });

  it('does not create a second dashboard KPI outside the team configuration', () => {
    const agent = record('1', 0.5, 0.9, { numerator: '1', denominator: '2' });
    agent.kpi_values!.push({
      ...agent.kpi_values![0],
      kpi_key: 'legacy_extra',
      label: 'Legacy Extra',
    });

    const result = aggregateConfiguredTeamKpis(
      [agent],
      config({ method: 'ratio', numerator_col: 'numerator', denominator_col: 'denominator' }),
    );

    expect([...result.values()].map((kpi) => kpi.label)).toEqual(['Configured Rate']);
  });

  it('supports weighted averages and summed volume KPIs from configuration', () => {
    const agents = [
      record('1', 2, 10, { volume: '10' }),
      record('2', 4, 20, { volume: '30' }),
    ];

    const weighted = aggregateConfiguredTeamKpis(
      agents,
      config({ method: 'weighted_average', weight_col: 'volume' }),
    ).get('configuredrate');
    const summed = aggregateConfiguredTeamKpis(agents, config({ method: 'sum' })).get('configuredrate');

    expect(weighted?.actual).toBeCloseTo(3.5);
    expect(weighted?.target).toBeCloseTo(15);
    expect(summed?.actual).toBeCloseTo(6);
    expect(summed?.target).toBeCloseTo(30);
  });

  it('respects the selected location for geographic ratio sources', () => {
    const agent = record('1', 0.5, 0.9, {});
    agent.geo = {
      bookings: { dubai: 10, sharjah: 20, ajman: 0, clinics: 0 },
      attended: { dubai: 8, sharjah: 10, ajman: 0, clinics: 0 },
    };
    const teamConfig = config({
      method: 'ratio',
      numerator_col: '$geo.attended',
      denominator_col: '$geo.bookings',
    });

    expect(aggregateConfiguredTeamKpis([agent], teamConfig, { location: 'dubai' }).get('configuredrate')?.actual)
      .toBeCloseTo(0.8);
    expect(aggregateConfiguredTeamKpis([agent], teamConfig, { location: 'all' }).get('configuredrate')?.actual)
      .toBeCloseTo(0.6);
  });
});

describe('calculateAggregatedTeamPerformance', () => {
  it('calculates the overall from pooled KPI totals instead of employee score averages', () => {
    const agents = [
      record('1', 0.5, 1, { numerator: '1', denominator: '2' }),
      record('2', 1, 1, { numerator: '9', denominator: '9' }),
    ];
    agents[0].evaluation.score = 10;
    agents[1].evaluation.score = 100;

    const performance = calculateAggregatedTeamPerformance(
      agents,
      config({ method: 'ratio', numerator_col: 'numerator', denominator_col: 'denominator' }),
    );

    expect(performance?.score).toBeCloseTo((10 / 11) * 100);
    expect(performance?.score).not.toBeCloseTo(55);
  });

  it('uses the Sales 100% scoring threshold after pooling source volumes', () => {
    const salesConfig = config({ method: 'ratio', numerator_col: 'actual_volume', denominator_col: 'target_volume' });
    salesConfig.kpis[0].score_target = 1;
    const performance = calculateAggregatedTeamPerformance([
      record('1', 105, 199, { actual_volume: '105', target_volume: '199' }),
      record('2', 222, 188, { actual_volume: '222', target_volume: '188' }),
    ], salesConfig);

    const pooledRate = 327 / 387;
    expect(performance?.kpis.get('configuredrate')?.actual).toBeCloseTo(pooledRate);
    expect(performance?.kpis.get('configuredrate')?.target).toBe(1);
    expect(performance?.kpis.get('configuredrate')?.contribution).toBeCloseTo(pooledRate * 100);
    expect(performance?.score).toBeCloseTo(pooledRate * 100);
  });

  it('applies the 80% baseline formula after pooling IP Final counters', () => {
    const baselineConfig = config({ method: 'ratio', numerator_col: 'numerator', denominator_col: 'denominator' });
    baselineConfig.kpis[0].score_formula = 'baseline_80';
    baselineConfig.kpis[0].cap_achievement = false;
    const agents = [
      record('1', 0.8, 1, { numerator: '8', denominator: '10' }),
      record('2', 1, 1, { numerator: '10', denominator: '10' }),
    ];

    const performance = calculateAggregatedTeamPerformance(agents, baselineConfig);

    expect(performance?.score).toBeCloseTo(50);
  });

  it('expresses position-specific KPI weights as their effective share of the team overall', () => {
    const positionConfig = validateTeamConfig({
      team: 'Position Team', db_name: 'Position Team', region: 'UAE',
      employee_id_col: 'EmployeeID', employee_name_col: 'EmployeeName',
      grade_thresholds: { A: 95, B: 85, C: 75, D: 65 },
      performance_levels: { Employee: { positions: {
        Alpha: { kpis: [{ key: 'alpha', label: 'Alpha KPI', weight: 1, direction: 'higher_better', unit: '%', color: '#10B981', actual_col: 'Actual', target_col: 'Target', aggregation: { method: 'average' } }] },
        Beta: { kpis: [{ key: 'beta', label: 'Beta KPI', weight: 1, direction: 'higher_better', unit: '%', color: '#3B82F6', actual_col: 'Actual', target_col: 'Target', aggregation: { method: 'average' } }] },
      } } },
    });
    const alpha = record('1', 1, 1, {});
    alpha.identity.team = 'Position Team';
    alpha.position = 'Alpha';
    alpha.kpi_values![0] = { ...alpha.kpi_values![0], kpi_key: 'alpha', label: 'Alpha KPI' };
    const beta = record('2', 1, 1, {});
    beta.identity.team = 'Position Team';
    beta.position = 'Beta';
    beta.kpi_values![0] = { ...beta.kpi_values![0], kpi_key: 'beta', label: 'Beta KPI' };

    const performance = calculateAggregatedTeamPerformance([alpha, beta], positionConfig);

    expect(performance?.score).toBe(100);
    expect(performance?.kpis.get('alphakpi')?.weight).toBe(0.5);
    expect(performance?.kpis.get('alphakpi')?.contribution).toBe(50);
    expect(performance?.kpis.get('betakpi')?.weight).toBe(0.5);
    expect(performance?.kpis.get('betakpi')?.contribution).toBe(50);
  });

  it('uses June Inbound reweighting and aggregates ratios and weighted AHT', () => {
    const inboundConfig = validateTeamConfig({
      team: 'Inbound', db_name: 'Inbound', region: 'EGY',
      employee_id_col: 'EmployeeID', employee_name_col: 'EmployeeName',
      grade_thresholds: { A: 95, B: 85, C: 75, D: 65 },
      kpis: [
        { key: 'Attendance', label: 'Attendance Rate', weight: 0.7, direction: 'higher_better', unit: '%', color: '#3B82F6', actual_col: 'Attend', target_col: 'AttendTarget', aggregation: { method: 'ratio', numerator_col: '$geo.attended', denominator_col: '$geo.bookings' } },
        { key: 'Booking', label: 'Booking Rate', weight: 0.1, direction: 'higher_better', unit: '%', color: '#10B981', actual_col: 'Booking', target_col: 'BookingTarget', aggregation: { method: 'ratio', numerator_col: '$geo.bookings', denominator_col: '$calls.total_handled' } },
        { key: 'Quality', label: 'Quality Score', weight: 0.05, direction: 'higher_better', unit: '%', color: '#8B5CF6', actual_col: 'Quality', target_col: 'QualityTarget', aggregation: { method: 'average' } },
        { key: 'AHT', label: 'AHT (Handle Time)', weight: 0.05, direction: 'lower_better', unit: 'min', color: '#6366F1', actual_col: 'AHT', target_col: 'AHTTarget', aggregation: { method: 'weighted_average', weight_col: '$calls.total_handled' } },
        { key: 'Other', label: 'Abandon Rate', weight: 0.1, direction: 'lower_better', unit: '%', color: '#EF4444', actual_col: 'Other', target_col: 'OtherTarget', aggregation: { method: 'ratio', numerator_col: '$calls.abandoned', denominator_col: '$calls.total_handled' } },
      ],
    });
    const makeInbound = (id: string, handled: number, bookings: number, attended: number, aht: number, utz: number): AgentRecord => ({
      ...record(id, 0, 1, {}),
      identity: { name: `Agent ${id}`, employee_id: id, team: 'Inbound', month: 'June' },
      calls: { inbound: handled, outbound: 0, total_handled: handled, abandoned: 0, aht_raw: '00:00:00' },
      geo: {
        bookings: { dubai: bookings, sharjah: 0, ajman: 0, clinics: 0 },
        attended: { dubai: attended, sharjah: 0, ajman: 0, clinics: 0 },
      },
      evaluation: { score: id === '1' ? 10 : 100, grade: 'E' },
      kpi_values: [
        { kpi_key: 'Attendance', label: 'Attendance Rate', unit: '%', direction: 'higher_better', actual_value: attended / bookings, target_value: 0.75, achievement_ratio: 0, weight_applied: 0.7, contribution: 0 },
        { kpi_key: 'Booking', label: 'Booking Rate', unit: '%', direction: 'higher_better', actual_value: bookings / handled, target_value: 0.45, achievement_ratio: 0, weight_applied: 0.1, contribution: 0 },
        { kpi_key: 'Quality', label: 'Quality Score', unit: '%', direction: 'higher_better', actual_value: 0, target_value: 0.95, achievement_ratio: 0, weight_applied: 0, contribution: 0 },
        { kpi_key: 'AHT', label: 'AHT (Handle Time)', unit: 'min', direction: 'lower_better', actual_value: aht, target_value: 2.5, achievement_ratio: 0, weight_applied: 0.05, contribution: 0 },
        { kpi_key: 'Other', label: 'UTZ', unit: '%', direction: 'higher_better', actual_value: utz, target_value: 0.85, achievement_ratio: 0, weight_applied: 0.15, contribution: 0 },
      ],
    });
    const performance = calculateAggregatedTeamPerformance([
      makeInbound('1', 200, 100, 60, 3, 0.8),
      makeInbound('2', 50, 50, 40, 2, 0.9),
    ], inboundConfig);

    expect(performance?.score).toBeCloseTo(91.6865, 3);
    expect(performance?.score).not.toBeCloseTo(55);
    expect(performance?.kpis.get('attendancerate')?.weight).toBe(0.7);
    expect(performance?.kpis.get('attendancerate')?.contribution).toBeCloseTo(62.2222, 3);
    expect(performance?.kpis.get('qualityscore')?.weight).toBe(0);
    expect(performance?.kpis.get('utz')?.weight).toBe(0.15);
    expect(performance?.kpis.get('utz')?.contribution).toBeCloseTo(15);
    expect([...performance!.kpis.values()].reduce((sum, kpi) => sum + (kpi.contribution ?? 0), 0))
      .toBeCloseTo(performance!.score);
  });
});
