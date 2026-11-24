import { beforeEach, describe, expect, it } from 'vitest';
import type { AgentRecord } from '../../types';
import {
  buildTeamKpiSixMonthTrends,
  clearTeamKpiSixMonthTrendsCache,
} from './kpiSixMonthTrend';

function makeAgent(name: string, month: string, bookings: number, attended: number): AgentRecord {
  return {
    identity: {
      id: `${name}-${month}`,
      name,
      team: 'Inbound',
      month,
      region: 'EGY',
    },
    geo: {
      bookings: { dubai: bookings, sharjah: 0, ajman: 0, clinics: 0 },
      attended: { dubai: attended, sharjah: 0, ajman: 0, clinics: 0 },
    },
    calls: {
      total_handled: Math.max(bookings * 2, 10),
      inbound: Math.max(bookings * 2, 10),
      abandoned: 0,
      aht_raw: '00:02:10',
    },
    actual: {
      reachability_rate: 0.72,
    },
    evaluation: {
      score: 88,
      grade: 'Average',
      status: 'Average',
    },
  } as unknown as AgentRecord;
}

describe('buildTeamKpiSixMonthTrends caching', () => {
  beforeEach(() => {
    clearTeamKpiSixMonthTrendsCache();
  });

  it('returns the cached trend map across repeated calls and freshly filtered arrays of the same records', () => {
    const a1 = makeAgent('Aya', 'June', 100, 70);
    const a2 = makeAgent('Aya', 'July', 100, 74);
    const agents = [a1, a2];

    const first = buildTeamKpiSixMonthTrends({
      agents,
      dashboardMonths: ['June', 'July'],
      activeMonth: 'July',
      teamConfig: undefined,
      location: 'all',
      teamId: 'inbound',
      isMergedTeam: false,
      isEgyptInbound: true,
      isOutbound: false,
    });

    // Exact same array ref -> instant WeakMap hit
    const second = buildTeamKpiSixMonthTrends({
      agents,
      dashboardMonths: ['June', 'July'],
      activeMonth: 'July',
      teamConfig: undefined,
      location: 'all',
      teamId: 'inbound',
      isMergedTeam: false,
      isEgyptInbound: true,
      isOutbound: false,
    });
    expect(second).toBe(first);

    // Newly allocated filtered array wrapping the exact same AgentRecord refs -> signature cache hit
    const third = buildTeamKpiSixMonthTrends({
      agents: [...agents],
      dashboardMonths: ['June', 'July'],
      activeMonth: 'July',
      teamConfig: undefined,
      location: 'all',
      teamId: 'inbound',
      isMergedTeam: false,
      isEgyptInbound: true,
      isOutbound: false,
    });
    expect(third).toBe(first);

    // Changing scope or record identity invalidates cleanly
    const fourth = buildTeamKpiSixMonthTrends({
      agents: [a1, makeAgent('Aya', 'July', 100, 82)],
      dashboardMonths: ['June', 'July'],
      activeMonth: 'July',
      teamConfig: undefined,
      location: 'all',
      teamId: 'inbound',
      isMergedTeam: false,
      isEgyptInbound: true,
      isOutbound: false,
    });
    expect(fourth).not.toBe(first);
    expect(fourth['Patient Attendance Rate']?.[1]?.actual).toBeCloseTo(82);
  });
});
