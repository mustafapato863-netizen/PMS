import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  buildCallCenterDeepDiveFromRecords,
  buildFunctionDeepDiveFromRecords,
  emptyMeasuredFunctionDeepDive,
} from './callCenterDeepDiveData';
import FunctionDeepDiveView from './components/FunctionDeepDiveView';
import type { ExecRecord } from '../executive/compose';

function makeRecord(
  employeeId: string,
  name: string,
  team: string,
  region: 'EGY' | 'UAE',
  periodKey: string,
  monthName: string,
  year: number,
  score: number,
  position = 'Specialist',
): ExecRecord {
  return {
    employeeId,
    name,
    team,
    region,
    position,
    level: 'Employee',
    branches: [],
    period: { year, month: monthName, key: periodKey },
    score,
    kpis: [],
  };
}

describe('Trend source parity', () => {
  it('generic headline change is null when the previous calendar month is a gap', () => {
    const records: ExecRecord[] = [
      makeRecord('hr1', 'Nour HR', 'Human Resources', 'EGY', '2026-08', 'August', 2026, 85.0),
      makeRecord('hr1', 'Nour HR', 'Human Resources', 'EGY', '2026-10', 'October', 2026, 91.0),
    ];
    const dive = buildFunctionDeepDiveFromRecords('human-resources', records, [], 'EGY', '2026-10');
    expect(dive.scoreTrend?.changeVsPrevious).toBeNull();
    expect(dive.headline.changeVsPrev).toBeNull();
    expect(dive.agentTeams[0]?.changeVsPrev).toBeNull();
  });

  it('Call Center channel change is null when the previous calendar month is a gap', () => {
    const records: ExecRecord[] = [
      makeRecord('inb1', 'Inbound Agent', 'Inbound', 'EGY', '2026-08', 'August', 2026, 80.0),
      makeRecord('out1', 'Outbound Agent', 'Outbound', 'EGY', '2026-08', 'August', 2026, 80.0),
      makeRecord('inb1', 'Inbound Agent', 'Inbound', 'EGY', '2026-10', 'October', 2026, 90.0),
      makeRecord('out1', 'Outbound Agent', 'Outbound', 'EGY', '2026-10', 'October', 2026, 90.0),
    ];
    const dive = buildCallCenterDeepDiveFromRecords(records, [], 'EGY', '2026-10');
    expect(dive.scoreTrend?.changeVsPrevious).toBeNull();
    expect(dive.headline.changeVsPrev).toBeNull();
    const inbound = dive.agentTeams.find((t) => t.teamSlug === 'inbound');
    const outbound = dive.agentTeams.find((t) => t.teamSlug === 'outbound');
    expect(inbound?.changeVsPrev).toBeNull();
    expect(outbound?.changeVsPrev).toBeNull();
  });

  it('Call Center trend leaves a support-only month as a gap', () => {
    const records: ExecRecord[] = [
      makeRecord('sup1', 'Trainer One', 'Call Center', 'EGY', '2026-09', 'September', 2026, 88.0, 'Trainer'),
      makeRecord('inb1', 'Inbound Agent', 'Inbound', 'EGY', '2026-10', 'October', 2026, 90.0),
      makeRecord('out1', 'Outbound Agent', 'Outbound', 'EGY', '2026-10', 'October', 2026, 80.0),
    ];
    const octDive = buildCallCenterDeepDiveFromRecords(records, [], 'EGY', '2026-10');
    const sepPoint = octDive.scoreTrend?.points.find((p) => p.periodKey === '2026-09');
    expect(sepPoint?.score).toBeNull();
    // A dive built for September alone is an empty state: no channel score exists.
    const sepDive = buildCallCenterDeepDiveFromRecords(records, [], 'EGY', '2026-09');
    expect(sepDive.isEmpty).toBe(true);
  });

  it('every Call Center trend point equals the headline of a dive built for that month', () => {
    const months: Array<[string, string, number]> = [
      ['2026-05', 'May', 2026],
      ['2026-06', 'June', 2026],
      ['2026-07', 'July', 2026],
      ['2026-08', 'August', 2026],
      ['2026-09', 'September', 2026],
      ['2026-10', 'October', 2026],
    ];
    const records: ExecRecord[] = [];
    months.forEach(([key, month, year], i) => {
      // Unequal headcounts: 2 Inbound, 1 Outbound, 1 Support.
      records.push(makeRecord('inb1', 'Inbound One', 'Inbound', 'EGY', key, month, year, 80 + i));
      records.push(makeRecord('inb2', 'Inbound Two', 'Inbound', 'EGY', key, month, year, 84 + i));
      records.push(makeRecord('out1', 'Outbound One', 'Outbound', 'EGY', key, month, year, 76 + i));
      records.push(makeRecord('sup1', 'Trainer One', 'Call Center', 'EGY', key, month, year, 88 + i, 'Trainer'));
    });
    const octDive = buildCallCenterDeepDiveFromRecords(records, [], 'EGY', '2026-10');
    for (const [key] of months) {
      const monthDive = buildCallCenterDeepDiveFromRecords(records, [], 'EGY', key);
      const point = octDive.scoreTrend?.points.find((p) => p.periodKey === key);
      expect(point?.score).toBe(monthDive.headline.score);
    }
    expect(octDive.scoreTrend?.changeVsPrevious).toBe(
      Number((octDive.headline.score - buildCallCenterDeepDiveFromRecords(records, [], 'EGY', '2026-09').headline.score).toFixed(1)),
    );
  });

  it('every generic trend point equals the headline of a dive built for that month, EGY and UAE', () => {
    const months: Array<[string, string, number]> = [
      ['2026-05', 'May', 2026],
      ['2026-06', 'June', 2026],
      ['2026-07', 'July', 2026],
      ['2026-08', 'August', 2026],
      ['2026-09', 'September', 2026],
      ['2026-10', 'October', 2026],
    ];
    for (const region of ['EGY', 'UAE'] as const) {
      const records: ExecRecord[] = [];
      months.forEach(([key, month, year], i) => {
        records.push(makeRecord('hr1', 'Nour HR', 'Human Resources', region, key, month, year, 80 + i));
        records.push(makeRecord('hr2', 'Sara HR', 'Human Resources', region, key, month, year, 90 + i));
      });
      const octDive = buildFunctionDeepDiveFromRecords('human-resources', records, [], region, '2026-10');
      for (const [key] of months) {
        const monthDive = buildFunctionDeepDiveFromRecords('human-resources', records, [], region, key);
        const point = octDive.scoreTrend?.points.find((p) => p.periodKey === key);
        expect(point?.score).toBe(monthDive.headline.score);
      }
    }
  });

  it('a missing channel in a trend month scores only the measured channels', () => {
    const records: ExecRecord[] = [
      makeRecord('inb1', 'Inbound Agent', 'Inbound', 'EGY', '2026-09', 'September', 2026, 88.0),
      makeRecord('inb1', 'Inbound Agent', 'Inbound', 'EGY', '2026-10', 'October', 2026, 92.0),
      makeRecord('out1', 'Outbound Agent', 'Outbound', 'EGY', '2026-10', 'October', 2026, 84.0),
    ];
    const octDive = buildCallCenterDeepDiveFromRecords(records, [], 'EGY', '2026-10');
    const sepPoint = octDive.scoreTrend?.points.find((p) => p.periodKey === '2026-09');
    // September has Inbound only: the point is the Inbound-only score,
    // matching a dive built for September, with no Outbound contribution.
    const sepDive = buildCallCenterDeepDiveFromRecords(records, [], 'EGY', '2026-09');
    expect(sepPoint?.score).toBe(sepDive.headline.score);
    expect(sepDive.agentTeams).toHaveLength(1);
    expect(sepDive.agentTeams[0]?.teamSlug).toBe('inbound');
    expect(octDive.scoreTrend?.changeVsPrevious).toBe(
      Number((octDive.headline.score - sepDive.headline.score).toFixed(1)),
    );
  });

  it('keeps Call Center Egypt and UAE trend points completely separate', () => {
    const records: ExecRecord[] = [
      makeRecord('inb1', 'Inbound EGY', 'Inbound', 'EGY', '2026-09', 'September', 2026, 88.0),
      makeRecord('out1', 'Outbound EGY', 'Outbound', 'EGY', '2026-09', 'September', 2026, 80.0),
      makeRecord('inb1', 'Inbound EGY', 'Inbound', 'EGY', '2026-10', 'October', 2026, 92.0),
      makeRecord('out1', 'Outbound EGY', 'Outbound', 'EGY', '2026-10', 'October', 2026, 84.0),
      makeRecord('inb9', 'Inbound UAE', 'Inbound', 'UAE', '2026-09', 'September', 2026, 70.0),
      makeRecord('out9', 'Outbound UAE', 'Outbound', 'UAE', '2026-09', 'September', 2026, 60.0),
      makeRecord('inb9', 'Inbound UAE', 'Inbound', 'UAE', '2026-10', 'October', 2026, 72.0),
      makeRecord('out9', 'Outbound UAE', 'Outbound', 'UAE', '2026-10', 'October', 2026, 64.0),
    ];
    const egyDive = buildCallCenterDeepDiveFromRecords(records, [], 'EGY', '2026-10');
    const uaeDive = buildCallCenterDeepDiveFromRecords(records, [], 'UAE', '2026-10');
    expect(egyDive.scoreTrend?.points.find((p) => p.periodKey === '2026-10')?.score).toBe(egyDive.headline.score);
    expect(uaeDive.scoreTrend?.points.find((p) => p.periodKey === '2026-10')?.score).toBe(uaeDive.headline.score);
    expect(egyDive.headline.score).not.toBe(uaeDive.headline.score);
    expect(egyDive.scoreTrend?.points.find((p) => p.periodKey === '2026-09')?.score).toBe(
      buildCallCenterDeepDiveFromRecords(records, [], 'EGY', '2026-09').headline.score,
    );
    expect(uaeDive.scoreTrend?.points.find((p) => p.periodKey === '2026-09')?.score).toBe(
      buildCallCenterDeepDiveFromRecords(records, [], 'UAE', '2026-09').headline.score,
    );
  });

  it('a function with no measured rows is an empty dive, never a 0.0% score', () => {
    const dive = buildFunctionDeepDiveFromRecords('human-resources', [], [], 'UAE', '2026-10');
    expect(dive.isEmpty).toBe(true);
    expect(dive.scoreTrend?.points).toEqual([]);
    expect(dive.scoreTrend?.changeVsPrevious).toBeNull();
    expect(emptyMeasuredFunctionDeepDive('human-resources', 'UAE', '2026-10').isEmpty).toBe(true);

    render(
      <FunctionDeepDiveView
        data={dive}
        roles={[]}
        onBackToOverview={() => {}}
        onSelectRole={() => {}}
      />,
    );
    expect(screen.getByTestId('deep-dive-empty-state')).toBeTruthy();
    expect(screen.getByText(/No measured Human Resources rows for UAE Region in October 2026/)).toBeTruthy();
    expect(screen.queryByTestId('deep-dive-function-score')).toBeNull();
    expect(screen.queryByTestId('function-score-trend')).toBeNull();
  });
});
