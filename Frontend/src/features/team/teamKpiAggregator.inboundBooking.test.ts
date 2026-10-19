import { describe, expect, it } from 'vitest';
import type { TeamConfig } from '../../schemas/teamConfig.schema';
import { applyInboundBookingDisplay, displayBookingRate, getKPIsForAgent, inboundBookingRateFromAgent, type AgentRecord } from '../../types';
import { resolveDisplayScore } from '../../utils/kpiScore';
import { aggregateConfiguredTeamKpis, calculateAggregatedTeamPerformance } from './teamKpiAggregator';

const inboundConfig = {
  team: 'Inbound',
  db_name: 'Inbound',
  region: 'EGY',
  kpis: [
    {
      key: 'Booking',
      label: 'Booking Rate',
      weight: 0.1,
      direction: 'higher_better',
      unit: '%',
      color: '#10B981',
      actual_col: 'A.Booking%',
      target_col: 'T.Booking%',
      aggregation: { method: 'ratio', numerator_col: '$geo.bookings', denominator_col: '$calls.total_handled' },
    },
  ],
} as unknown as TeamConfig;

function inboundAgent(name: string, bookings: number, inbound: number, handled: number, staleRate: number): AgentRecord {
  return {
    identity: { name, month: 'September', team: 'Inbound', employee_id: name },
    calls: { inbound, outbound: handled - inbound, total_handled: handled, abandoned: 0, aht_raw: '00:02:30' },
    geo: {
      bookings: { dubai: bookings, sharjah: 0, ajman: 0, clinics: 0 },
      attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
    },
    actual: { booking_rate: staleRate, attend_rate: 0, abandon_rate: 0 },
    achievement: { booking_ach: staleRate / 0.45, attend_ach: 0 },
    evaluation: { score: 80, grade: 'C' },
    raw_data: { 'A.Booking%': String(staleRate), 'T.Booking%': '0.45' },
    kpi_values: [
      {
        kpi_key: 'Booking',
        label: 'Booking Rate',
        unit: '%',
        direction: 'higher_better',
        actual_value: staleRate,
        target_value: 0.45,
        achievement_ratio: Math.min(staleRate / 0.45, 1),
        weight_applied: 0.1,
        contribution: 0.1,
      },
    ],
  };
}

describe('Inbound Booking CR', () => {
  it('uses inbound calls for each agent and for the pooled team total', () => {
    const first = inboundAgent('A', 40, 100, 150, 40 / 150);
    const second = inboundAgent('B', 20, 50, 80, 20 / 80);

    expect(getKPIsForAgent(first).find((kpi) => kpi.label === 'Booking Rate')?.actual).toBeCloseTo(40 / 100);
    expect(getKPIsForAgent(second).find((kpi) => kpi.label === 'Booking Rate')?.actual).toBeCloseTo(20 / 50);

    const total = aggregateConfiguredTeamKpis([first, second], inboundConfig).get('bookingrate');
    expect(total?.actual).toBeCloseTo(60 / 150);
    expect(total?.actual).not.toBeCloseTo(60 / 230);
  });

  it('rebuilds an agent booking rate from raw counters when geo bookings are empty', () => {
    const agent = inboundAgent('A', 40, 100, 150, 40 / 150);
    agent.calls.inbound = 0;
    agent.geo.bookings = { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 };
    agent.raw_data = { ...agent.raw_data, Dubai_Booking: '40', InboundCalls: '100' };

    expect(getKPIsForAgent(agent).find((kpi) => kpi.label === 'Booking Rate')?.actual).toBeCloseTo(40 / 100);
  });

  it('recomputes the agent score from bookings divided by inbound calls', () => {
    const agent = inboundAgent('A', 40, 100, 150, 40 / 150);
    agent.evaluation.score = 80;
    agent.kpi_values = [
      {
        kpi_key: 'Attendance',
        label: 'Attendance Rate',
        unit: '%',
        direction: 'higher_better',
        actual_value: 0.8,
        target_value: 0.75,
        achievement_ratio: 1,
        weight_applied: 0.7,
        contribution: 0.7,
      },
      ...(agent.kpi_values ?? []),
    ];

    const booking = getKPIsForAgent(agent).find((kpi) => kpi.label === 'Booking Rate');
    const bookingAchievement = Math.min((40 / 100) / 0.45, 1) * 100;
    expect(booking?.actual).toBeCloseTo(40 / 100);
    expect(booking?.achievement).toBeCloseTo(bookingAchievement);

    const score = resolveDisplayScore(agent, undefined);
    expect(score).toBeCloseTo(Math.round((100 * 0.7 + bookingAchievement * 0.1) * 100) / 100);
    expect(score).not.toBe(80);

    const team = calculateAggregatedTeamPerformance([agent], inboundConfig);
    expect(team?.kpis.get('bookingrate')?.actual).toBeCloseTo(40 / 100);
    expect(team?.score).not.toBe(80);
  });

  it('keeps the stored booking rate when inbound calls exist but booking counters do not', () => {
    const agent = inboundAgent('A', 40, 100, 150, 40 / 150);
    agent.geo.bookings = { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 };
    agent.raw_data = { 'A.Booking%': String(40 / 150), 'T.Booking%': '0.45' };

    expect(inboundBookingRateFromAgent(agent)).toBeNull();
    expect(displayBookingRate(agent)).toBeCloseTo(40 / 150);
  });

  it('rewrites a stored booking KPI that still uses handled calls', () => {
    const agent = inboundAgent('A', 40, 100, 150, 40 / 150);
    const displayed = applyInboundBookingDisplay(agent);
    const booking = displayed.kpi_values?.find((kpi) => kpi.kpi_key === 'Booking');

    expect(displayed.actual.booking_rate).toBeCloseTo(40 / 100);
    expect(booking?.actual_value).toBeCloseTo(40 / 100);
    expect(booking?.achievement_ratio).toBeCloseTo(Math.min((40 / 100) / 0.45, 1));
    expect(booking?.contribution).toBeCloseTo(Math.min((40 / 100) / 0.45, 1) * 0.1);
  });
});
