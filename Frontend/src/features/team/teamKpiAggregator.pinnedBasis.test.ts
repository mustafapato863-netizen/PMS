import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { mapScopedPerformanceRecord } from '../../hooks/usePerformanceData';
import { validateTeamConfig } from '../../schemas/teamConfig.schema';
import type { TeamConfig } from '../../schemas/teamConfig.schema';
import type { AgentRecord } from '../../types';
import { buildTeamKpiAnalysis } from './teamKpiAnalysis';
import { aggregateConfiguredTeamKpis, calculateAggregatedTeamPerformance, displayedTeamScore, recordsUseAppliedPin } from './teamKpiAggregator';

const ATTENDANCE_POOLED = (0.5 / 0.7) * 0.5 * 100;
const PRODUCTIVITY_ACTUAL = 0.7780694444444445;
const PRODUCTIVITY_POOLED = (PRODUCTIVITY_ACTUAL / 0.8) * 0.2 * 100;

const outboundConfig = {
  team: 'Outbound',
  db_name: 'Outbound',
  region: 'EGY',
  kpis: [
    {
      key: 'Attendance',
      label: 'Attendance Rate',
      weight: 0.7,
      direction: 'higher_better',
      unit: '%',
      color: '#3B82F6',
      actual_col: 'A.Attend%',
      target_col: 'T.Attend%',
      aggregation: { method: 'ratio', numerator_col: '$geo.attended', denominator_col: '$geo.bookings' },
    },
  ],
} as unknown as TeamConfig;

function outboundAgent(pinned: boolean, target = 0.7): AgentRecord {
  return {
    identity: { name: 'Anonymous Agent', month: 'August', team: 'Outbound', employee_id: 'ANON-1' },
    calls: { inbound: 0, outbound: 10, total_handled: 10, abandoned: 0, aht_raw: '00:02:30' },
    geo: {
      bookings: { dubai: 20, sharjah: 0, ajman: 0, clinics: 0 },
      attended: { dubai: 10, sharjah: 0, ajman: 0, clinics: 0 },
    },
    actual: { booking_rate: 0.3, attend_rate: 0.46065259117082535, abandon_rate: 0, quality_rate: 0.98, reachability_rate: 0.57 },
    achievement: { booking_ach: 0, attend_ach: 0.5 },
    evaluation: { score: 79.93, grade: 'C' },
    raw_data: {
      'T.Attend%': '0.65',
      'A.Attend%': '0.46065259117082535',
      'T.Productivity%': '0.8',
      Productivity: '0.7780694444444445',
    },
    kpi_values: [
      {
        kpi_key: 'Attendance',
        label: 'Attendance Rate',
        unit: '%',
        direction: 'higher_better',
        actual_value: 0.46065259117082535,
        target_value: target,
        achievement_ratio: Math.min(0.46065259117082535 / target, 1),
        weight_applied: 0.5,
        contribution: 0.329,
        evaluation_pinned: pinned,
      },
      {
        kpi_key: 'Productivity',
        label: 'Productivity',
        unit: '%',
        direction: 'higher_better',
        actual_value: 0.7780694444444445,
        target_value: 0.8,
        achievement_ratio: Math.min(0.7780694444444445 / 0.8, 1),
        weight_applied: 0.2,
        contribution: 0.1945,
        evaluation_pinned: pinned,
      },
    ],
  };
}

describe('pinned monthly evaluation basis on team KPI tiles', () => {
  it('scores pooled actuals with the applied target and weight', () => {
    const agent = outboundAgent(true);
    const result = calculateAggregatedTeamPerformance([agent], outboundConfig);
    const attendance = result?.kpis.get('attendancerate');
    const productivity = result?.kpis.get('productivity');

    expect(attendance?.target).toBe(0.7);
    expect(attendance?.weight).toBe(0.5);
    expect(attendance?.actual).toBe(0.5);
    expect(attendance?.contribution).toBe(ATTENDANCE_POOLED);
    expect(productivity?.weight).toBe(0.2);
    expect(productivity?.target).toBe(0.8);
    expect(productivity?.actual).toBe(PRODUCTIVITY_ACTUAL);
    expect(productivity?.contribution).toBe(PRODUCTIVITY_POOLED);
    expect(result?.score).toBe(Math.min(ATTENDANCE_POOLED + PRODUCTIVITY_POOLED, 100));
    expect(result?.score).not.toBe(agent.evaluation.score);
    expect(agent.raw_data?.['T.Attend%']).toBe('0.65');
    expect(agent.raw_data?.Productivity).toBe('0.7780694444444445');
  });

  it('still uses the workbook target for an unpinned legacy ratio row', () => {
    const result = calculateAggregatedTeamPerformance([outboundAgent(false)], outboundConfig);
    const attendance = result?.kpis.get('attendancerate');

    expect(attendance?.target).toBe(0.65);
    expect(attendance?.weight).toBe(0.7);
    expect(result?.kpis.has('productivity')).toBe(false);
  });

  it('scores each attendance basis on its own and does not publish a zero team score', () => {
    const second = outboundAgent(true, 0.65);
    second.identity = { ...second.identity, employee_id: 'ANON-2', name: 'Second Agent' };
    const attendanceAt65 = (0.5 / 0.65) * 0.5 * 100;
    const cohortAt70 = Math.min(ATTENDANCE_POOLED + PRODUCTIVITY_POOLED, 100);
    const cohortAt65 = Math.min(attendanceAt65 + PRODUCTIVITY_POOLED, 100);
    const combined = (cohortAt70 + cohortAt65) / 2;
    const forward = calculateAggregatedTeamPerformance([outboundAgent(true, 0.7), second], outboundConfig);
    const reversed = calculateAggregatedTeamPerformance([second, outboundAgent(true, 0.7)], outboundConfig);
    const attendance = forward?.kpis.get('attendancerate');
    const productivity = forward?.kpis.get('productivity');

    expect(attendance?.basisVaries).toBe(true);
    expect(attendance?.weight).toBeNull();
    expect(attendance?.contribution).toBeNull();
    expect(Number.isNaN(attendance?.target)).toBe(true);
    expect(attendance?.target).not.toBe(0.675);
    expect(attendance?.actual).toBe(0.5);
    expect(productivity?.basisVaries).not.toBe(true);
    expect(productivity?.contribution).toBe(PRODUCTIVITY_POOLED);
    expect(forward?.score).toBe(combined);
    expect(forward?.score).not.toBe(0);
    expect(reversed?.score).toBe(forward?.score);
    expect(reversed?.kpis.get('attendancerate')?.basisVaries).toBe(true);
    expect(Number.isNaN(reversed?.kpis.get('attendancerate')?.target)).toBe(true);
  });

  it('flags opposite directions, units, and KPI identities in the direct aggregate', () => {
    const higher = outboundAgent(true, 0.7);
    const lower = outboundAgent(true, 0.7);
    lower.identity = { ...lower.identity, employee_id: 'ANON-2', name: 'Lower Agent' };
    lower.kpi_values = (lower.kpi_values ?? []).map((kpi) => (
      kpi.kpi_key === 'Attendance' ? { ...kpi, direction: 'lower_better' } : kpi
    ));
    const otherUnit = outboundAgent(true, 0.7);
    otherUnit.identity = { ...otherUnit.identity, employee_id: 'ANON-3', name: 'Other unit' };
    otherUnit.kpi_values = (otherUnit.kpi_values ?? []).map((kpi) => (
      kpi.kpi_key === 'Attendance' ? { ...kpi, unit: 'number' } : kpi
    ));
    const otherIdentity = outboundAgent(true, 0.7);
    otherIdentity.identity = { ...otherIdentity.identity, employee_id: 'ANON-4', name: 'Other identity' };
    otherIdentity.kpi_values = (otherIdentity.kpi_values ?? []).map((kpi) => (
      kpi.kpi_key === 'Attendance' ? { ...kpi, kpi_key: 'AttendPct' } : kpi
    ));

    const forward = aggregateConfiguredTeamKpis([higher, lower], outboundConfig).get('attendancerate');
    const reverse = aggregateConfiguredTeamKpis([lower, higher], outboundConfig).get('attendancerate');
    const unitForward = aggregateConfiguredTeamKpis([higher, otherUnit], outboundConfig).get('attendancerate');
    const unitReverse = aggregateConfiguredTeamKpis([otherUnit, higher], outboundConfig).get('attendancerate');
    const identityForward = aggregateConfiguredTeamKpis([higher, otherIdentity], outboundConfig).get('attendancerate');
    const identityReverse = aggregateConfiguredTeamKpis([otherIdentity, higher], outboundConfig).get('attendancerate');

    for (const attendance of [forward, reverse, unitForward, unitReverse, identityForward, identityReverse]) {
      expect(attendance?.basisVaries).toBe(true);
      expect(attendance?.isLowerBetter).toBeUndefined();
      expect(attendance?.weight).toBeNull();
      expect(attendance?.contribution).toBeNull();
      expect(Number.isNaN(attendance?.target)).toBe(true);
    }
    expect(forward?.actual).toBe(0.5);
    expect(reverse?.actual).toBe(0.5);
    expect(forward?.unit).toBe('%');
    expect(forward?.key).toBe('Attendance');
    for (const attendance of [unitForward, unitReverse, identityForward, identityReverse]) {
      expect(Number.isNaN(attendance?.actual)).toBe(true);
    }
    const otherTarget = outboundAgent(true, 0.65);
    otherTarget.identity = { ...otherTarget.identity, employee_id: 'ANON-5', name: 'Other target' };
    for (const ordered of [[higher, otherTarget], [otherTarget, higher]] as const) {
      const targetOnly = aggregateConfiguredTeamKpis([...ordered], outboundConfig).get('attendancerate');
      expect(targetOnly?.basisVaries).toBe(true);
      expect(targetOnly?.actual).toBe(0.5);
      expect(targetOnly?.unit).toBe('%');
      expect(targetOnly?.key).toBe('Attendance');
    }
    expect(aggregateConfiguredTeamKpis([higher], outboundConfig).get('attendancerate')?.basisVaries).not.toBe(true);
  });

  it('does not pool opposite directions that share a target and weight', () => {
    const lower = outboundAgent(true, 0.7);
    lower.identity = { ...lower.identity, employee_id: 'ANON-2', name: 'Lower Agent' };
    lower.kpi_values = (lower.kpi_values ?? []).map((kpi) => (
      kpi.kpi_key === 'Attendance' ? { ...kpi, direction: 'lower_better' } : kpi
    ));
    const higherScore = Math.min(ATTENDANCE_POOLED + PRODUCTIVITY_POOLED, 100);
    const lowerAttendance = Math.min((0.7 / 0.5) * 100, 100) * 0.5;
    const lowerScore = Math.min(lowerAttendance + PRODUCTIVITY_POOLED, 100);
    const forward = calculateAggregatedTeamPerformance([outboundAgent(true, 0.7), lower], outboundConfig);
    const reversed = calculateAggregatedTeamPerformance([lower, outboundAgent(true, 0.7)], outboundConfig);
    const attendance = forward?.kpis.get('attendancerate');

    expect(attendance?.basisVaries).toBe(true);
    expect(attendance?.isLowerBetter).toBeUndefined();
    expect(reversed?.kpis.get('attendancerate')?.isLowerBetter).toBeUndefined();
    expect(attendance?.weight).toBeNull();
    expect(attendance?.contribution).toBeNull();
    expect(forward?.score).toBe((higherScore + lowerScore) / 2);
    expect(forward?.score).not.toBe(0);
    expect(reversed?.score).toBe(forward?.score);
  });

  it('combines different pinned KPI sets by headcount without averaging attendance targets', () => {
    const withProductivity = outboundAgent(true);
    const attendanceOnly = outboundAgent(true);
    attendanceOnly.identity = { ...attendanceOnly.identity, employee_id: 'ANON-2', name: 'Attendance only' };
    attendanceOnly.kpi_values = (attendanceOnly.kpi_values ?? []).filter((kpi) => kpi.kpi_key === 'Attendance');
    const result = calculateAggregatedTeamPerformance([withProductivity, attendanceOnly], outboundConfig);
    const attendance = result?.kpis.get('attendancerate');
    const productivity = result?.kpis.get('productivity');
    const withProductivityScore = Math.min(ATTENDANCE_POOLED + PRODUCTIVITY_POOLED, 100);
    const attendanceOnlyScore = Math.min(ATTENDANCE_POOLED, 100);

    expect(attendance?.target).toBe(0.7);
    expect(attendance?.weight).toBe(0.5);
    expect(attendance?.contribution).toBe(ATTENDANCE_POOLED);
    expect(attendance?.basisVaries).not.toBe(true);
    expect(productivity?.contribution).toBe(PRODUCTIVITY_POOLED / 2);
    expect(productivity?.weight).toBe(0.1);
    expect(result?.score).toBe((withProductivityScore + attendanceOnlyScore) / 2);
  });
});

describe('pinned basis through the live record mapper and outbound file', () => {
  const outboundFile = validateTeamConfig(JSON.parse(readFileSync(
    resolve(process.cwd(), '../Backend/config/teams/outbound.json'),
    'utf8',
  )));

  it('keeps the reviewer probe target and weight, and the original raw target', () => {
    const agent = mapScopedPerformanceRecord({
      id: 'synthetic-review-row',
      employee_id: 'SYNTHETIC-REVIEW',
      employee_name: 'Synthetic review',
      team: 'Outbound',
      month: 'August',
      year: 2026,
      performance_level: 'Employee',
      score: 79.93,
      raw_data: { 'A.Attend%': 0.46, 'T.Attend%': 0.65 },
      kpi_values: [{
        kpi_key: 'Attendance',
        label: 'Attendance Rate',
        unit: '%',
        actual_value: 0.46,
        target_value: 0.7,
        achievement_ratio: 0.46 / 0.7,
        weight_applied: 0.5,
        contribution: (0.46 / 0.7) * 0.5,
        direction: 'higher_better',
        evaluation_pinned: true,
      }],
      evaluation_basis: { pinned: true, version_id: 'synthetic-approved-revision' },
    });
    const displayed = aggregateConfiguredTeamKpis([agent], outboundFile).get('attendancerate');
    const scored = calculateAggregatedTeamPerformance([agent], outboundFile)?.kpis.get('attendancerate');

    expect(displayed?.target).toBe(0.7);
    expect(scored?.weight).toBe(0.5);
    expect(agent.raw_data?.['T.Attend%']).toBe(0.65);
  });

  it('keeps pinned productivity and does not let static analysis weights replace the applied pin', () => {
    const agent = mapScopedPerformanceRecord({
      id: 'synthetic-review-row',
      employee_id: 'SYNTHETIC-REVIEW',
      employee_name: 'Synthetic review',
      team: 'Outbound',
      month: 'August',
      year: 2026,
      performance_level: 'Employee',
      score: 79.93,
      raw_data: {
        'A.Attend%': 0.46065259117082535,
        'T.Attend%': 0.65,
        Productivity: PRODUCTIVITY_ACTUAL,
        'T.Productivity%': 0.8,
      },
      geo: {
        bookings: { dubai: 20, sharjah: 0, ajman: 0, clinics: 0 },
        attended: { dubai: 10, sharjah: 0, ajman: 0, clinics: 0 },
      },
      kpi_values: [
        {
          kpi_key: 'Attendance',
          label: 'Attendance Rate',
          unit: '%',
          actual_value: 0.46065259117082535,
          target_value: 0.7,
          achievement_ratio: Math.min(0.46065259117082535 / 0.7, 1),
          weight_applied: 0.5,
          contribution: 0.329,
          direction: 'higher_better',
          evaluation_pinned: true,
        },
        {
          kpi_key: 'Productivity',
          label: 'Productivity',
          unit: '%',
          actual_value: PRODUCTIVITY_ACTUAL,
          target_value: 0.8,
          achievement_ratio: Math.min(PRODUCTIVITY_ACTUAL / 0.8, 1),
          weight_applied: 0.2,
          contribution: 0.1945,
          direction: 'higher_better',
          evaluation_pinned: true,
        },
      ],
    });
    const scored = calculateAggregatedTeamPerformance([agent], outboundFile);
    const analysis = buildTeamKpiAnalysis([agent], [], {
      teamConfig: outboundFile,
      teamWeights: { Attendance: 0.7, Booking: 0.1, Quality: 0.1, Other: 0.1 },
    });
    const attendance = analysis.find((row) => row.label === 'Attendance Rate');
    const productivity = analysis.find((row) => row.label === 'Productivity');

    expect(scored?.kpis.get('productivity')?.weight).toBe(0.2);
    expect(scored?.kpis.get('productivity')?.contribution).toBe(PRODUCTIVITY_POOLED);
    expect(scored?.kpis.get('attendancerate')?.contribution).toBe(ATTENDANCE_POOLED);
    expect(attendance?.target).toBe(0.7);
    expect(attendance?.weight).toBe(0.5);
    expect(attendance?.contribution).toBe(ATTENDANCE_POOLED);
    expect(productivity?.weight).toBe(0.2);
    expect(productivity?.contribution).toBe(PRODUCTIVITY_POOLED);
    expect(agent.raw_data?.['T.Attend%']).toBe(0.65);
    expect(agent.raw_data?.Productivity).toBe(PRODUCTIVITY_ACTUAL);
    expect(agent.evaluation.score).toBe(79.93);
    expect(scored?.score).not.toBe(79.93);
    expect(recordsUseAppliedPin([agent])).toBe(true);
    expect(displayedTeamScore(scored?.score ?? null, agent.evaluation.score, true)).toBe(scored?.score);
  });

  it('flags opposite applied directions in the direct aggregate for either input order', () => {
    const agent = mapScopedPerformanceRecord({
      id: 'synthetic-review-row',
      employee_id: 'SYNTHETIC-REVIEW',
      employee_name: 'Synthetic review',
      team: 'Outbound',
      month: 'August',
      year: 2026,
      performance_level: 'Employee',
      score: 79.93,
      raw_data: { 'A.Attend%': 0.46, 'T.Attend%': 0.65 },
      kpi_values: [{
        kpi_key: 'Attendance',
        label: 'Attendance Rate',
        unit: '%',
        actual_value: 0.46,
        target_value: 0.7,
        achievement_ratio: 0.46 / 0.7,
        weight_applied: 0.5,
        contribution: (0.46 / 0.7) * 0.5,
        direction: 'higher_better',
        evaluation_pinned: true,
      }],
      evaluation_basis: { pinned: true, version_id: 'synthetic-approved-revision' },
    });
    agent.geo.bookings.dubai = 20;
    agent.geo.attended.dubai = 10;
    const opposite = {
      ...agent,
      identity: { ...agent.identity, employee_id: 'SYNTHETIC-OPPOSITE' },
      kpi_values: (agent.kpi_values ?? []).map((kpi) => ({ ...kpi, direction: 'lower_better' as const })),
    };
    const forward = aggregateConfiguredTeamKpis([agent, opposite], outboundFile).get('attendancerate');
    const reverse = aggregateConfiguredTeamKpis([opposite, agent], outboundFile).get('attendancerate');

    expect(forward?.basisVaries).toBe(true);
    expect(reverse?.basisVaries).toBe(true);
    expect(forward?.isLowerBetter).toBeUndefined();
    expect(reverse?.isLowerBetter).toBeUndefined();
    expect(forward?.weight).toBeNull();
    expect(reverse?.weight).toBeNull();
    expect(Number.isNaN(forward?.target)).toBe(true);
    expect(Number.isNaN(reverse?.target)).toBe(true);
  });

  it('does not merge pinned cohorts that share a label but not a unit or KPI identity', () => {
    const agent = mapScopedPerformanceRecord({
      id: 'synthetic-review-row',
      employee_id: 'SYNTHETIC-REVIEW',
      employee_name: 'Synthetic review',
      team: 'Outbound',
      month: 'August',
      year: 2026,
      performance_level: 'Employee',
      score: 79.93,
      raw_data: { 'A.Attend%': 0.46, 'T.Attend%': 0.65 },
      kpi_values: [{
        kpi_key: 'Attendance',
        label: 'Attendance Rate',
        unit: '%',
        actual_value: 0.46,
        target_value: 0.7,
        achievement_ratio: 0.46 / 0.7,
        weight_applied: 0.5,
        contribution: (0.46 / 0.7) * 0.5,
        direction: 'higher_better',
        evaluation_pinned: true,
      }],
    });
    agent.geo.bookings.dubai = 20;
    agent.geo.attended.dubai = 10;
    const other = (override: { unit?: string; kpi_key?: string }, actual: number) => ({
      ...agent,
      identity: { ...agent.identity, employee_id: 'SYNTHETIC-DISTINCT' },
      kpi_values: (agent.kpi_values ?? []).map((kpi) => ({ ...kpi, ...override, actual_value: actual })),
    });
    const assertVaried = (override: { unit?: string; kpi_key?: string }, actual: number) => {
      const distinct = other(override, actual);
      const average = (0.46 + actual) / 2;
      for (const ordered of [[agent, distinct], [distinct, agent]] as const) {
        const result = calculateAggregatedTeamPerformance([...ordered], outboundFile);
        const varied = result?.kpis.get('attendancerate');
        expect(result?.basisVaries).toBe(true);
        expect(varied?.basisVaries).toBe(true);
        expect(varied?.weight).toBeNull();
        expect(varied?.contribution).toBeNull();
        expect(Number.isNaN(varied?.target)).toBe(true);
        expect(Number.isNaN(varied?.actual)).toBe(true);
        expect(varied?.actual).not.toBe(average);
        expect(result?.score).toBe(calculateAggregatedTeamPerformance([ordered[1], ordered[0]], outboundFile)?.score);
      }
    };

    const uniform = calculateAggregatedTeamPerformance([agent], outboundFile)?.kpis.get('attendancerate');
    expect(uniform?.key).toBe('Attendance');
    expect(uniform?.unit).toBe('%');
    expect(uniform?.basisVaries).not.toBe(true);

    assertVaried({ unit: 'count' }, 0.9);
    assertVaried({ kpi_key: 'Distinct Attendance' }, 0.2);
    const counted = other({ unit: 'count' }, 0.9);
    const keyed = other({ kpi_key: 'Distinct Attendance' }, 0.2);
    for (const ordered of [[agent, counted], [counted, agent]] as const) {
      const direct = aggregateConfiguredTeamKpis([...ordered], outboundFile).get('attendancerate');
      expect(direct?.basisVaries).toBe(true);
      expect(direct?.unit).toBeUndefined();
      expect(direct?.key).toBe('Attendance');
      expect(Number.isNaN(direct?.actual)).toBe(true);
    }
    for (const ordered of [[agent, keyed], [keyed, agent]] as const) {
      const direct = aggregateConfiguredTeamKpis([...ordered], outboundFile).get('attendancerate');
      expect(direct?.basisVaries).toBe(true);
      expect(direct?.unit).toBe('%');
      expect(direct?.key).toBeUndefined();
      expect(Number.isNaN(direct?.actual)).toBe(true);
    }
  });
});

describe('legacy multi-position rollup', () => {
  const positionConfig = {
    team: 'Synthetic Positions',
    db_name: 'Synthetic Positions',
    region: 'EGY',
    kpis: [],
    performance_levels: {
      Employee: {
        positions: {
          Agent: {
            kpis: [{
              key: 'Quality', label: 'Quality Score', weight: 0.4, direction: 'higher_better', unit: '%', color: '#3B82F6',
            }],
          },
          Lead: {
            kpis: [{
              key: 'Quality', label: 'Quality Score', weight: 0.6, direction: 'lower_better', unit: '%', color: '#3B82F6',
            }],
          },
        },
      },
    },
  } as unknown as TeamConfig;

  function positionAgent(position: 'Agent' | 'Lead', pinned = false, target = position === 'Agent' ? 100 : 50): AgentRecord {
    const weight = position === 'Agent' ? 0.4 : 0.6;
    return {
      identity: {
        name: position, month: 'August', team: 'Synthetic Positions', employee_id: position, position,
      },
      position,
      calls: { inbound: 0, outbound: 0, total_handled: 0, abandoned: 0, aht_raw: '00:00:00' },
      geo: {
        bookings: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
        attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
      },
      actual: { booking_rate: 0, attend_rate: 0, abandon_rate: 0, quality_rate: 0.8, reachability_rate: 0 },
      achievement: { booking_ach: 0, attend_ach: 0 },
      evaluation: { score: 80, grade: 'C' },
      raw_data: {},
      kpi_values: [{
        kpi_key: 'Quality',
        label: 'Quality Score',
        unit: '%',
        direction: position === 'Lead' ? 'lower_better' : 'higher_better',
        actual_value: 80,
        target_value: target,
        achievement_ratio: 0.8,
        weight_applied: weight,
        contribution: 0.3,
        evaluation_pinned: pinned,
      }],
    };
  }

  it('keeps a headcount average for legacy position variation and does not label it as an applied pin', () => {
    const forward = calculateAggregatedTeamPerformance(
      [positionAgent('Agent'), positionAgent('Lead')],
      positionConfig,
    );
    const reversed = calculateAggregatedTeamPerformance(
      [positionAgent('Lead'), positionAgent('Agent')],
      positionConfig,
    );
    const quality = forward?.kpis.get('qualityscore');
    const agentContribution = (80 / 100) * 100 * 0.4;
    const leadContribution = (50 / 80) * 100 * 0.6;

    expect(quality?.evaluationPinned).not.toBe(true);
    expect(quality?.basisVaries).not.toBe(true);
    expect(quality?.target).toBe(75);
    expect(quality?.weight).toBe(0.5);
    expect(quality?.contribution).toBe((agentContribution + leadContribution) / 2);
    expect(forward?.score).toBe((agentContribution + leadContribution) / 2);
    expect(forward?.score).not.toBe(0);
    expect(reversed?.score).toBe(forward?.score);
    expect(reversed?.kpis.get('qualityscore')?.target).toBe(75);
    expect(reversed?.kpis.get('qualityscore')?.evaluationPinned).not.toBe(true);
  });

  it('still blanks metadata when applied pins disagree across positions', () => {
    const agent = positionAgent('Agent', true, 0.7);
    const lead = positionAgent('Lead', true, 0.65);
    lead.kpi_values = (lead.kpi_values ?? []).map((kpi) => ({ ...kpi, direction: 'higher_better', weight_applied: 0.5 }));
    const result = calculateAggregatedTeamPerformance([agent, lead], positionConfig);
    const quality = result?.kpis.get('qualityscore');

    expect(quality?.basisVaries).toBe(true);
    expect(quality?.evaluationPinned).toBe(true);
    expect(quality?.weight).toBeNull();
    expect(quality?.contribution).toBeNull();
    expect(Number.isNaN(quality?.target)).toBe(true);
    expect(quality?.target).not.toBe(0.675);
    expect(result?.score).not.toBe(0);
  });
});

describe('displayed team score', () => {
  it('keeps a pinned pooled score when it is more than 15 points from the employee average', () => {
    expect(displayedTeamScore(55.16, 79.93, true)).toBe(55.16);
    expect(displayedTeamScore(0, 79.93, true)).toBe(0);
    expect(displayedTeamScore(null, 79.93, true)).toBe(79.93);
  });

  it('keeps the legacy 15-point guard when no applied pin is present', () => {
    expect(displayedTeamScore(55.16, 79.93, false)).toBe(79.93);
    expect(displayedTeamScore(70, 79.93, false)).toBe(70);
    expect(displayedTeamScore(0, 79.93, false)).toBe(79.93);
    expect(recordsUseAppliedPin([{ kpi_values: [{ evaluation_pinned: false }] }])).toBe(false);
  });
});
