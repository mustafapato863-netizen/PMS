import { describe, expect, it } from 'vitest';
import {
  composeExecutiveSummary,
  type ComposeInput,
  type ExecRecord,
} from './compose';
import { FIXTURE_TEAM_FUNCTIONS, fixtureActions, fixtureDrivers } from './executive.fixture';

const TODAY = new Date(2026, 6, 6); // 6 Jul 2026 (local)

function period(year: number, month: string, key: string) {
  return { year, month, key };
}

let seq = 0;
function rec(
  team: string,
  periodKey: string,
  monthName: string,
  year: number,
  score: number,
  position = 'Agent L1',
): ExecRecord {
  seq += 1;
  return {
    employeeId: `e${seq}`,
    name: `E ${seq}`,
    team,
    region: 'EGY',
    position,
    level: 'Employee',
    branches: [],
    period: period(year, monthName, periodKey),
    score,
    kpis: [],
  };
}

function compose(records: ExecRecord[]) {
  return composeExecutiveSummary({
    view: 'corporate',
    role: 'Admin',
    records,
    filters: {},
    teamFunctions: FIXTURE_TEAM_FUNCTIONS,
    drivers: fixtureDrivers(),
    actions: fixtureActions(TODAY),
    comparisonRecords: records,
    today: TODAY,
  } satisfies ComposeInput);
}

describe('executive Call Center function-card trend uses one scoring basis (Item 3a)', () => {
  it('uses the channel-averaged score for every trend month, not a plain record mean', () => {
    // April: Inbound 2 agents at 90, Outbound 1 agent at 60.
    // Plain record mean = (90 + 90 + 60) / 3 = 80.0.
    // Channel-averaged headline = (90 + 60) / 2 = 75.0 — the deep-dive basis.
    // May and June have equal headcounts, so both bases agree there (80.0, 85.0).
    const records: ExecRecord[] = [
      rec('Inbound', '2026-04', 'April', 2026, 90),
      rec('Inbound', '2026-04', 'April', 2026, 90),
      rec('Outbound', '2026-04', 'April', 2026, 60),
      rec('Inbound', '2026-05', 'May', 2026, 80),
      rec('Outbound', '2026-05', 'May', 2026, 80),
      rec('Inbound', '2026-06', 'June', 2026, 85),
      rec('Outbound', '2026-06', 'June', 2026, 85),
    ];
    const summary = compose(records);
    const cc = summary.functions.find((card) => card.function === 'Call Center');
    expect(cc).toBeDefined();
    expect(cc!.score).toBe(85);
    expect(cc!.previous_score).toBe(80);
    const byKey = new Map(cc!.trend.map((point) => [point.period.key, point.score]));
    // The older month must match a deep dive built for that month, not the
    // plain record mean of 80.0.
    expect(byKey.get('2026-04')).toBe(75);
    expect(byKey.get('2026-05')).toBe(80);
    expect(byKey.get('2026-06')).toBe(85);
  });

  it('leaves a support-only month as a null trend point, like the deep dive', () => {
    const records: ExecRecord[] = [
      // March: support-position rows only — no measured channel score.
      rec('Call Center', '2026-03', 'March', 2026, 88, 'Trainer'),
      rec('Inbound', '2026-04', 'April', 2026, 90),
      rec('Outbound', '2026-04', 'April', 2026, 60),
      rec('Inbound', '2026-05', 'May', 2026, 80),
      rec('Outbound', '2026-05', 'May', 2026, 80),
      rec('Inbound', '2026-06', 'June', 2026, 85),
      rec('Outbound', '2026-06', 'June', 2026, 85),
    ];
    const summary = compose(records);
    const cc = summary.functions.find((card) => card.function === 'Call Center');
    expect(cc).toBeDefined();
    const byKey = new Map(cc!.trend.map((point) => [point.period.key, point.score]));
    expect(byKey.get('2026-03')).toBeNull();
    expect(byKey.get('2026-04')).toBe(75);
  });

  it('reports no Call Center score when the effective month has support rows only', () => {
    const records: ExecRecord[] = [
      rec('Inbound', '2026-05', 'May', 2026, 80),
      rec('Outbound', '2026-05', 'May', 2026, 80),
      // June: support-position rows only — the deep dive is an empty state.
      rec('Call Center', '2026-06', 'June', 2026, 88, 'Trainer'),
    ];
    const summary = compose(records);
    const cc = summary.functions.find((card) => card.function === 'Call Center');
    expect(cc).toBeDefined();
    expect(cc!.score).toBeNull();
    expect(cc!.previous_score).toBe(80);
    expect(cc!.change).toBeNull();
    const byKey = new Map(cc!.trend.map((point) => [point.period.key, point.score]));
    expect(byKey.get('2026-06')).toBeNull();
    expect(byKey.get('2026-05')).toBe(80);
  });
});
