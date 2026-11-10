import { describe, expect, it } from 'vitest';
import {
  buildFunctionScoreTrend,
  buildCallCenterDeepDiveFromRecords,
  buildFunctionDeepDiveFromRecords,
  emptyMeasuredFunctionDeepDive,
} from './callCenterDeepDiveData';
import type { ExecRecord } from '../executive/compose';

function makePeriod(year: number, month: string, key: string) {
  return { year, month, key };
}

function makeRecord(
  employeeId: string,
  name: string,
  team: string,
  _functionName: string,
  region: 'EGY' | 'UAE',
  periodKey: string,
  monthName: string,
  year: number,
  score: number,
): ExecRecord {
  return {
    employeeId,
    name,
    team,
    region,
    position: 'Specialist',
    level: 'Employee',
    branches: [],
    period: makePeriod(year, monthName, periodKey),
    score,
    kpis: [],
  };
}

describe('Six-Month Function Score Trend', () => {
  const oct2026 = makePeriod(2026, 'October', '2026-10');

  it('generates 6 chronological points ending at the selected month', () => {
    const hrRecords: ExecRecord[] = [
      makeRecord('hr1', 'Nour HR', 'Human Resources', 'Human Resources', 'EGY', '2026-05', 'May', 2026, 88.0),
      makeRecord('hr1', 'Nour HR', 'Human Resources', 'Human Resources', 'EGY', '2026-06', 'June', 2026, 89.0),
      makeRecord('hr1', 'Nour HR', 'Human Resources', 'Human Resources', 'EGY', '2026-07', 'July', 2026, 90.0),
      makeRecord('hr1', 'Nour HR', 'Human Resources', 'Human Resources', 'EGY', '2026-08', 'August', 2026, 91.0),
      makeRecord('hr1', 'Nour HR', 'Human Resources', 'Human Resources', 'EGY', '2026-09', 'September', 2026, 92.0),
      makeRecord('hr1', 'Nour HR', 'Human Resources', 'Human Resources', 'EGY', '2026-10', 'October', 2026, 94.5),
    ];

    const trend = buildFunctionScoreTrend(hrRecords, oct2026, 94.5);
    expect(trend.points).toHaveLength(6);
    expect(trend.points.map((p) => p.periodKey)).toEqual([
      '2026-05',
      '2026-06',
      '2026-07',
      '2026-08',
      '2026-09',
      '2026-10',
    ]);
    expect(trend.points.map((p) => p.month)).toEqual(['May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct']);
    expect(trend.points[5].selected).toBe(true);
    expect(trend.points[4].selected).toBe(false);
  });

  it('guarantees the selected point matches the displayed function score', () => {
    const hrRecords: ExecRecord[] = [
      makeRecord('hr1', 'Nour HR', 'Human Resources', 'Human Resources', 'EGY', '2026-09', 'September', 2026, 85.0),
      makeRecord('hr1', 'Nour HR', 'Human Resources', 'Human Resources', 'EGY', '2026-10', 'October', 2026, 92.4),
    ];

    const dive = buildFunctionDeepDiveFromRecords('human-resources', hrRecords, [], 'EGY', '2026-10');
    expect(dive.headline.score).toBe(92.4);
    expect(dive.scoreTrend?.points).toBeDefined();

    const selectedPoint = dive.scoreTrend!.points.find((p) => p.selected);
    expect(selectedPoint).toBeDefined();
    expect(selectedPoint?.periodKey).toBe('2026-10');
    expect(selectedPoint?.score).toBe(dive.headline.score);
  });

  it('ensures previous-month point and displayed month-over-month value agree on the same basis', () => {
    const hrRecords: ExecRecord[] = [
      makeRecord('hr1', 'Nour HR', 'Human Resources', 'Human Resources', 'EGY', '2026-09', 'September', 2026, 88.0),
      makeRecord('hr2', 'Sara HR', 'Human Resources', 'Human Resources', 'EGY', '2026-09', 'September', 2026, 90.0),
      makeRecord('hr1', 'Nour HR', 'Human Resources', 'Human Resources', 'EGY', '2026-10', 'October', 2026, 93.0),
      makeRecord('hr2', 'Sara HR', 'Human Resources', 'Human Resources', 'EGY', '2026-10', 'October', 2026, 95.0),
    ];

    const dive = buildFunctionDeepDiveFromRecords('human-resources', hrRecords, [], 'EGY', '2026-10');
    // September avg: (88 + 90)/2 = 89.0
    // October avg: (93 + 95)/2 = 94.0
    // Diff: 94.0 - 89.0 = +5.0
    expect(dive.headline.score).toBe(94.0);
    expect(dive.scoreTrend?.changeVsPrevious).toBe(5.0);
    expect(dive.headline.changeVsPrev).toBe(5.0);
    expect(dive.previousMonthLabel).toBe('September');

    const sepPoint = dive.scoreTrend!.points.find((p) => p.periodKey === '2026-09');
    const octPoint = dive.scoreTrend!.points.find((p) => p.periodKey === '2026-10');
    expect(sepPoint?.score).toBe(89.0);
    expect(octPoint?.score).toBe(94.0);
    expect(Number((octPoint!.score! - sepPoint!.score!).toFixed(1))).toBe(dive.headline.changeVsPrev);
  });

  it('leaves missing months as gaps (null) and does not fabricate change vs missing months', () => {
    // September is intentionally missing; only August and October exist
    const hrRecords: ExecRecord[] = [
      makeRecord('hr1', 'Nour HR', 'Human Resources', 'Human Resources', 'EGY', '2026-08', 'August', 2026, 85.0),
      makeRecord('hr1', 'Nour HR', 'Human Resources', 'Human Resources', 'EGY', '2026-10', 'October', 2026, 91.0),
    ];

    const dive = buildFunctionDeepDiveFromRecords('human-resources', hrRecords, [], 'EGY', '2026-10');
    const points = dive.scoreTrend!.points;

    // Missing months: May (idx 0), June (idx 1), July (idx 2), September (idx 4)
    expect(points[0].score).toBeNull();
    expect(points[1].score).toBeNull();
    expect(points[2].score).toBeNull();
    expect(points[3].score).toBe(85.0); // August
    expect(points[4].score).toBeNull(); // September is a gap
    expect(points[5].score).toBe(91.0); // October

    // Since September is missing, changeVsPrevious is null and NOT computed across the gap
    expect(dive.scoreTrend?.changeVsPrevious).toBeNull();
  });

  it('keeps Egypt and UAE records and calculations completely separate', () => {
    const mixedRecords: ExecRecord[] = [
      makeRecord('egy1', 'Ahmed EGY', 'Human Resources', 'Human Resources', 'EGY', '2026-09', 'September', 2026, 90.0),
      makeRecord('egy1', 'Ahmed EGY', 'Human Resources', 'Human Resources', 'EGY', '2026-10', 'October', 2026, 95.0),
      makeRecord('uae1', 'Rashid UAE', 'Human Resources', 'Human Resources', 'UAE', '2026-09', 'September', 2026, 70.0),
      makeRecord('uae1', 'Rashid UAE', 'Human Resources', 'Human Resources', 'UAE', '2026-10', 'October', 2026, 72.0),
    ];

    const egyptDive = buildFunctionDeepDiveFromRecords('human-resources', mixedRecords, [], 'EGY', '2026-10');
    const uaeDive = buildFunctionDeepDiveFromRecords('human-resources', mixedRecords, [], 'UAE', '2026-10');

    expect(egyptDive.headline.score).toBe(95.0);
    expect(egyptDive.scoreTrend?.points.find((p) => p.periodKey === '2026-10')?.score).toBe(95.0);
    expect(egyptDive.scoreTrend?.points.find((p) => p.periodKey === '2026-09')?.score).toBe(90.0);
    expect(egyptDive.scoreTrend?.changeVsPrevious).toBe(5.0);

    expect(uaeDive.headline.score).toBe(72.0);
    expect(uaeDive.scoreTrend?.points.find((p) => p.periodKey === '2026-10')?.score).toBe(72.0);
    expect(uaeDive.scoreTrend?.points.find((p) => p.periodKey === '2026-09')?.score).toBe(70.0);
    expect(uaeDive.scoreTrend?.changeVsPrevious).toBe(2.0);
  });

  it('supports Call Center 6-month score trend with channel scoring', () => {
    const ccRecords: ExecRecord[] = [
      makeRecord('inb1', 'Inbound Agent 1', 'Inbound', 'Call Center', 'EGY', '2026-09', 'September', 2026, 88.0),
      makeRecord('out1', 'Outbound Agent 1', 'Outbound', 'Call Center', 'EGY', '2026-09', 'September', 2026, 80.0),
      makeRecord('inb1', 'Inbound Agent 1', 'Inbound', 'Call Center', 'EGY', '2026-10', 'October', 2026, 92.0),
      makeRecord('out1', 'Outbound Agent 1', 'Outbound', 'Call Center', 'EGY', '2026-10', 'October', 2026, 84.0),
    ];

    const ccDive = buildCallCenterDeepDiveFromRecords(ccRecords, [], 'EGY', '2026-10');
    expect(ccDive.scoreTrend).toBeDefined();
    expect(ccDive.scoreTrend!.points).toHaveLength(6);

    const octPoint = ccDive.scoreTrend!.points.find((p) => p.selected);
    expect(octPoint?.score).toBe(ccDive.headline.score);

    const sepPoint = ccDive.scoreTrend!.points.find((p) => p.periodKey === '2026-09');
    expect(sepPoint?.score).not.toBeNull();
    if (sepPoint?.score !== null && octPoint?.score !== null) {
      expect(ccDive.scoreTrend?.changeVsPrevious).toBe(
        Number((octPoint!.score! - sepPoint!.score!).toFixed(1)),
      );
    }
  });

  it('provides an honest empty state with empty points when no records exist', () => {
    const emptyDive = emptyMeasuredFunctionDeepDive('human-resources', 'UAE');
    expect(emptyDive.scoreTrend).toBeDefined();
    expect(emptyDive.scoreTrend!.points).toEqual([]);
    expect(emptyDive.scoreTrend!.changeVsPrevious).toBeNull();
  });

  it('updates the 6-month trailing window and selected point when changing reporting month', () => {
    const records: ExecRecord[] = [
      makeRecord('hr1', 'Nour HR', 'Human Resources', 'Human Resources', 'EGY', '2026-04', 'April', 2026, 80.0),
      makeRecord('hr1', 'Nour HR', 'Human Resources', 'Human Resources', 'EGY', '2026-05', 'May', 2026, 82.0),
      makeRecord('hr1', 'Nour HR', 'Human Resources', 'Human Resources', 'EGY', '2026-06', 'June', 2026, 84.0),
      makeRecord('hr1', 'Nour HR', 'Human Resources', 'Human Resources', 'EGY', '2026-07', 'July', 2026, 86.0),
      makeRecord('hr1', 'Nour HR', 'Human Resources', 'Human Resources', 'EGY', '2026-08', 'August', 2026, 88.0),
      makeRecord('hr1', 'Nour HR', 'Human Resources', 'Human Resources', 'EGY', '2026-09', 'September', 2026, 90.0),
      makeRecord('hr1', 'Nour HR', 'Human Resources', 'Human Resources', 'EGY', '2026-10', 'October', 2026, 92.0),
    ];

    const sepDive = buildFunctionDeepDiveFromRecords('human-resources', records, [], 'EGY', '2026-09');
    expect(sepDive.scoreTrend!.points.map((p) => p.periodKey)).toEqual([
      '2026-04',
      '2026-05',
      '2026-06',
      '2026-07',
      '2026-08',
      '2026-09',
    ]);
    expect(sepDive.scoreTrend!.points.find((p) => p.selected)?.periodKey).toBe('2026-09');
    expect(sepDive.headline.score).toBe(90.0);

    const octDive = buildFunctionDeepDiveFromRecords('human-resources', records, [], 'EGY', '2026-10');
    expect(octDive.scoreTrend!.points.map((p) => p.periodKey)).toEqual([
      '2026-05',
      '2026-06',
      '2026-07',
      '2026-08',
      '2026-09',
      '2026-10',
    ]);
    expect(octDive.scoreTrend!.points.find((p) => p.selected)?.periodKey).toBe('2026-10');
    expect(octDive.headline.score).toBe(92.0);
  });

  it('correctly scopes records when switching functions', () => {
    const multiFunctionRecords: ExecRecord[] = [
      makeRecord('hr1', 'HR Person', 'Human Resources', 'Human Resources', 'EGY', '2026-10', 'October', 2026, 85.0),
      makeRecord('mkt1', 'MKT Person', 'Marketing', 'Marketing', 'EGY', '2026-10', 'October', 2026, 96.0),
    ];

    const hrDive = buildFunctionDeepDiveFromRecords('human-resources', multiFunctionRecords, [], 'EGY', '2026-10');
    const mktDive = buildFunctionDeepDiveFromRecords('marketing', multiFunctionRecords, [], 'EGY', '2026-10');

    expect(hrDive.headline.score).toBe(85.0);
    expect(hrDive.scoreTrend!.points.find((p) => p.selected)?.score).toBe(85.0);

    expect(mktDive.headline.score).toBe(96.0);
    expect(mktDive.scoreTrend!.points.find((p) => p.selected)?.score).toBe(96.0);
  });

  it('includes both Egypt Resubmission aliases in the same RCM function trend', () => {
    const rcmRecords: ExecRecord[] = [
      makeRecord('emp1', 'Moustafa', 'Resubmission', 'RCM', 'EGY', '2026-09', 'September', 2026, 80.0),
      makeRecord('emp2', 'Fatma', 'Re-Submission EGY', 'RCM', 'EGY', '2026-09', 'September', 2026, 90.0),
      makeRecord('emp1', 'Moustafa', 'Resubmission', 'RCM', 'EGY', '2026-10', 'October', 2026, 85.0),
      makeRecord('emp2', 'Fatma', 'Re-Submission EGY', 'RCM', 'EGY', '2026-10', 'October', 2026, 95.0),
    ];

    const rcmDive = buildFunctionDeepDiveFromRecords('rcm', rcmRecords, [], 'EGY', '2026-10');
    // In October: emp1 (85.0) and emp2 (95.0) -> mean = 90.0
    expect(rcmDive.headline.score).toBe(90.0);
    expect(rcmDive.scoreTrend!.points.find((p) => p.selected)?.score).toBe(90.0);

    // September includes each employee once through both approved Egypt aliases.
    const sepPoint = rcmDive.scoreTrend!.points.find((p) => p.periodKey === '2026-09');
    expect(sepPoint?.score).toBe(85.0);
    expect(rcmDive.scoreTrend!.changeVsPrevious).toBe(5.0);
  });
});
