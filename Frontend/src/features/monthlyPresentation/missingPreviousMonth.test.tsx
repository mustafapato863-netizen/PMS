import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  buildCallCenterDeepDiveFromRecords,
  buildFunctionDeepDiveFromRecords,
} from './callCenterDeepDiveData';
import { buildTeamDeepDiveFromRecords } from './teamDeepDiveData';
import { resolveRoleCards } from './roleDetailData';
import CallCenterDeepDiveView from './components/CallCenterDeepDiveView';
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
    // One measured KPI row so the channel diagnosis carries the change text.
    kpis: [
      {
        kpi_key: 'booking-rate',
        label: 'Booking Rate',
        unit: 'percent',
        direction: 'higher_better',
        actual_value: 90,
        target_value: 95,
        achievement_ratio: 0.95,
        weight_applied: 0.4,
        contribution: 1,
      },
    ],
  };
}

const SEP = ['2026-09', 'September', 2026] as const;
const OCT = ['2026-10', 'October', 2026] as const;
const AUG = ['2026-08', 'August', 2026] as const;

function ccRecords(
  region: 'EGY' | 'UAE',
  inbound: Array<[string, number]>,
  outbound: Array<[string, number]>,
): ExecRecord[] {
  const records: ExecRecord[] = [];
  for (const [key, score] of inbound) {
    records.push(
      makeRecord('inb1', 'Inbound Agent', 'Inbound', region, key, key === '2026-09' ? 'September' : key === '2026-10' ? 'October' : 'August', 2026, score),
    );
  }
  for (const [key, score] of outbound) {
    records.push(
      makeRecord('out1', 'Outbound Agent', 'Outbound', region, key, key === '2026-09' ? 'September' : key === '2026-10' ? 'October' : 'August', 2026, score),
    );
  }
  return records;
}

describe('Missing previous-month values are never shown as 0%', () => {
  it.each(['EGY', 'UAE'] as const)(
    'October data with no September data reports null changes, never +0.0% (%s)',
    (region) => {
      const records = ccRecords(region, [['2026-10', 90]], [['2026-10', 84]]);
      const dive = buildCallCenterDeepDiveFromRecords(records, [], region, '2026-10');

      expect(dive.scoreTrend?.points.find((p) => p.periodKey === '2026-09')?.score).toBeNull();
      expect(dive.scoreTrend?.changeVsPrevious).toBeNull();
      expect(dive.headline.changeVsPrev).toBeNull();
      expect(dive.agentTeams.find((t) => t.teamSlug === 'inbound')?.changeVsPrev).toBeNull();
      expect(dive.agentTeams.find((t) => t.teamSlug === 'outbound')?.changeVsPrev).toBeNull();
      // The channel diagnoses must not print a fake change either.
      expect(dive.agentTeams[0]?.diagnosis).toContain('no September data to compare');
      expect(dive.agentTeams[1]?.diagnosis).toContain('no September data to compare');

      const generic = buildFunctionDeepDiveFromRecords(
        'human-resources',
        [
          makeRecord('hr1', 'Nour HR', 'Human Resources', region, '2026-10', 'October', 2026, 91.0),
        ],
        [],
        region,
        '2026-10',
      );
      expect(generic.headline.changeVsPrev).toBeNull();
      expect(generic.agentTeams[0]?.changeVsPrev).toBeNull();

      const team = buildTeamDeepDiveFromRecords(
        'inbound',
        [makeRecord('inb1', 'Inbound Agent', 'Inbound', region, '2026-10', 'October', 2026, 90.0)],
        [],
        region,
        '2026-10',
      );
      expect(team.summary.changeVsPrev).toBeNull();
      expect(team.scoreTrend?.changeVsPrevious).toBeNull();

      render(
        <CallCenterDeepDiveView
          data={dive}
          onBackToOverview={() => {}}
          onSelectAgentTeam={() => {}}
          onSelectRole={() => {}}
        />,
      );
      expect(screen.getByText('— No previous-month data')).toBeTruthy();
      const inboundCard = screen.getByTestId('agent-team-card-inbound-agents');
      expect(inboundCard.textContent).not.toContain('+0.0%');
      expect(inboundCard.textContent).toContain('—');
    },
  );

  it.each(['EGY', 'UAE'] as const)(
    'October and September with the same measured score preserve a real 0.0%% change (%s)',
    (region) => {
      const records = ccRecords(
        region,
        [
          ['2026-09', 90],
          ['2026-10', 90],
        ],
        [
          ['2026-09', 84],
          ['2026-10', 84],
        ],
      );
      const dive = buildCallCenterDeepDiveFromRecords(records, [], region, '2026-10');
      expect(dive.headline.changeVsPrev).toBe(0);
      expect(dive.agentTeams.find((t) => t.teamSlug === 'inbound')?.changeVsPrev).toBe(0);
      expect(dive.agentTeams.find((t) => t.teamSlug === 'outbound')?.changeVsPrev).toBe(0);

      const generic = buildFunctionDeepDiveFromRecords(
        'human-resources',
        [
          makeRecord('hr1', 'Nour HR', 'Human Resources', region, '2026-09', 'September', 2026, 91.0),
          makeRecord('hr1', 'Nour HR', 'Human Resources', region, '2026-10', 'October', 2026, 91.0),
        ],
        [],
        region,
        '2026-10',
      );
      expect(generic.headline.changeVsPrev).toBe(0);
      expect(generic.agentTeams[0]?.changeVsPrev).toBe(0);

      render(
        <CallCenterDeepDiveView
          data={dive}
          onBackToOverview={() => {}}
          onSelectAgentTeam={() => {}}
          onSelectRole={() => {}}
        />,
      );
      // A real measured zero change is still displayed as 0.0%.
      expect(screen.queryByText('— No previous-month data')).toBeNull();
      expect(screen.getByTestId('agent-team-card-inbound-agents').textContent).toContain('+0.0%');
    },
  );

  it('October and September with a positive or negative change report the measured change', () => {
    const up = buildCallCenterDeepDiveFromRecords(
      ccRecords('EGY', [['2026-09', 85], ['2026-10', 90]], [['2026-09', 80], ['2026-10', 86]]),
      [],
      'EGY',
      '2026-10',
    );
    expect(up.headline.changeVsPrev).toBeGreaterThan(0);
    expect(up.agentTeams.find((t) => t.teamSlug === 'inbound')?.changeVsPrev).toBe(5);
    expect(up.agentTeams.find((t) => t.teamSlug === 'outbound')?.changeVsPrev).toBe(6);

    const down = buildCallCenterDeepDiveFromRecords(
      ccRecords('EGY', [['2026-09', 90], ['2026-10', 85]], [['2026-09', 86], ['2026-10', 80]]),
      [],
      'EGY',
      '2026-10',
    );
    expect(down.headline.changeVsPrev).toBeLessThan(0);
    expect(down.agentTeams.find((t) => t.teamSlug === 'inbound')?.changeVsPrev).toBe(-5);
    expect(down.agentTeams.find((t) => t.teamSlug === 'outbound')?.changeVsPrev).toBe(-6);

    const team = buildTeamDeepDiveFromRecords(
      'inbound',
      [
        makeRecord('inb1', 'Inbound Agent', 'Inbound', 'EGY', '2026-09', 'September', 2026, 85.0),
        makeRecord('inb1', 'Inbound Agent', 'Inbound', 'EGY', '2026-10', 'October', 2026, 90.0),
      ],
      [],
      'EGY',
      '2026-10',
    );
    expect(team.summary.changeVsPrev).toBe(5);
  });

  it('one channel missing the previous month shows null for that channel only', () => {
    const records: ExecRecord[] = [
      makeRecord('inb1', 'Inbound Agent', 'Inbound', 'EGY', '2026-09', 'September', 2026, 88.0),
      makeRecord('inb1', 'Inbound Agent', 'Inbound', 'EGY', '2026-10', 'October', 2026, 92.0),
      makeRecord('out1', 'Outbound Agent', 'Outbound', 'EGY', '2026-10', 'October', 2026, 84.0),
    ];
    const dive = buildCallCenterDeepDiveFromRecords(records, [], 'EGY', '2026-10');
    expect(dive.agentTeams.find((t) => t.teamSlug === 'inbound')?.changeVsPrev).toBe(4);
    expect(dive.agentTeams.find((t) => t.teamSlug === 'outbound')?.changeVsPrev).toBeNull();

    render(
      <CallCenterDeepDiveView
        data={dive}
        onBackToOverview={() => {}}
        onSelectAgentTeam={() => {}}
        onSelectRole={() => {}}
      />,
    );
    const outboundCard = screen.getByTestId('agent-team-card-outbound-agents');
    expect(outboundCard.textContent).not.toContain('+0.0%');
    expect(outboundCard.textContent).toContain('—');
    expect(screen.getByTestId('agent-team-card-inbound-agents').textContent).toContain('+4.0%');
  });

  it('role cards report null when the previous month is missing and never compare against August', () => {
    const records: ExecRecord[] = [
      // Fatma has August and October only: September is a gap, so no movement.
      makeRecord('hr1', 'Fatma HR', 'Human Resources', 'EGY', '2026-08', 'August', 2026, 80.0, 'HR Specialist'),
      makeRecord('hr1', 'Fatma HR', 'Human Resources', 'EGY', '2026-10', 'October', 2026, 95.0, 'HR Specialist'),
      // Sara has September and October: a real measured movement.
      makeRecord('hr2', 'Sara HR', 'Human Resources', 'EGY', '2026-09', 'September', 2026, 90.0, 'HR Specialist'),
      makeRecord('hr2', 'Sara HR', 'Human Resources', 'EGY', '2026-10', 'October', 2026, 96.0, 'HR Specialist'),
    ];
    const dive = buildFunctionDeepDiveFromRecords('human-resources', records, [], 'EGY', '2026-10');
    const cards = resolveRoleCards(dive, records);
    const fatma = cards.flatMap((c) => c.members).find((m) => m.personName === 'Fatma HR');
    const sara = cards.flatMap((c) => c.members).find((m) => m.personName === 'Sara HR');
    // Fatma: August 80 -> October 95 would be +15 if compared across the
    // gap; the correct answer is null.
    expect(fatma?.changeVsPrev).toBeNull();
    expect(sara?.changeVsPrev).toBe(6);

    render(
      <FunctionDeepDiveView
        data={dive}
        roles={cards}
        onBackToOverview={() => {}}
        onSelectRole={() => {}}
      />,
    );
    // The role board shows the measured +6.0% for Sara and "—" for Fatma.
    expect(screen.getByText('+6.0%')).toBeTruthy();
    expect(screen.queryByText('+15.0%')).toBeNull();
  });

  it('Call Center role detail reports null when the previous month is missing', () => {
    const records: ExecRecord[] = [
      makeRecord('inb1', 'Inbound Agent', 'Inbound', 'EGY', '2026-08', 'August', 2026, 80.0),
      makeRecord('inb1', 'Inbound Agent', 'Inbound', 'EGY', '2026-10', 'October', 2026, 95.0),
      makeRecord('out1', 'Outbound Agent', 'Outbound', 'EGY', '2026-10', 'October', 2026, 84.0),
    ];
    const dive = buildCallCenterDeepDiveFromRecords(records, [], 'EGY', '2026-10');
    const cards = resolveRoleCards(dive, records);
    const inbound = cards.flatMap((c) => c.members).find((m) => m.personName === 'Inbound Agent');
    expect(inbound?.changeVsPrev).toBeNull();
  });

  it('a missing intermediate month in the six-month chart is a null point with null change', () => {
    const months: Array<[string, string, number]> = [
      ['2026-05', 'May', 80],
      ['2026-06', 'June', 82],
      ['2026-07', 'July', 84],
      ['2026-08', 'August', 86],
      // September 2026 is missing entirely.
      ['2026-10', 'October', 90],
    ];
    const records: ExecRecord[] = months.flatMap(([key, month, score]) => [
      makeRecord('inb1', 'Inbound Agent', 'Inbound', 'EGY', key, month, 2026, score),
      makeRecord('out1', 'Outbound Agent', 'Outbound', 'EGY', key, month, 2026, score - 4),
    ]);
    const dive = buildCallCenterDeepDiveFromRecords(records, [], 'EGY', '2026-10');
    expect(dive.scoreTrend?.points).toHaveLength(6);
    expect(dive.scoreTrend?.points.find((p) => p.periodKey === '2026-09')?.score).toBeNull();
    expect(dive.scoreTrend?.points.find((p) => p.periodKey === '2026-10')?.score).toBe(
      dive.headline.score,
    );
    expect(dive.scoreTrend?.changeVsPrevious).toBeNull();
    expect(dive.headline.changeVsPrev).toBeNull();
    expect(dive.agentTeams.find((t) => t.teamSlug === 'inbound')?.changeVsPrev).toBeNull();
    expect(dive.agentTeams.find((t) => t.teamSlug === 'outbound')?.changeVsPrev).toBeNull();

    const generic = buildFunctionDeepDiveFromRecords(
      'human-resources',
      months.map(([key, month, score]) =>
        makeRecord('hr1', 'Nour HR', 'Human Resources', 'EGY', key, month, 2026, score),
      ),
      [],
      'EGY',
      '2026-10',
    );
    expect(generic.scoreTrend?.points.find((p) => p.periodKey === '2026-09')?.score).toBeNull();
    expect(generic.scoreTrend?.changeVsPrevious).toBeNull();
    expect(generic.headline.changeVsPrev).toBeNull();
  });
});

// Referenced so the month constants stay in sync with the cases above.
void SEP;
void OCT;
void AUG;
