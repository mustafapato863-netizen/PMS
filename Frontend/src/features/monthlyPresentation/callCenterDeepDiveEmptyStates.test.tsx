import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  buildCallCenterDeepDiveFromRecords,
  emptyMeasuredFunctionDeepDive,
} from './callCenterDeepDiveData';
import CallCenterDeepDiveView from './components/CallCenterDeepDiveView';
import type { ExecRecord } from '../executive/compose';

function makePeriod(year: number, month: string, key: string) {
  return { year, month, key };
}

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
    period: makePeriod(year, monthName, periodKey),
    score,
    kpis: [],
  };
}

function inboundOutbound(
  region: 'EGY' | 'UAE',
  periodKey: string,
  monthName: string,
  year: number,
  inboundScore: number,
  outboundScore: number,
): ExecRecord[] {
  return [
    makeRecord('inb1', 'Inbound Agent', 'Inbound', region, periodKey, monthName, year, inboundScore),
    makeRecord('out1', 'Outbound Agent', 'Outbound', region, periodKey, monthName, year, outboundScore),
  ];
}

describe('Call Center Deep Dive — truthful empty states (Task 1)', () => {
  it('UAE single-channel dive does not crash on the empty UAE fallback and omits the missing channel', () => {
    const records: ExecRecord[] = [
      makeRecord('inb1', 'Inbound Agent', 'Inbound', 'UAE', '2026-09', 'September', 2026, 80),
      makeRecord('inb1', 'Inbound Agent', 'Inbound', 'UAE', '2026-10', 'October', 2026, 80),
    ];
    const dive = buildCallCenterDeepDiveFromRecords(records, [], 'UAE', '2026-10');

    expect(dive.agentTeams).toHaveLength(1);
    expect(dive.agentTeams[0].teamSlug).toBe('inbound');
    expect(dive.agentTeams.map((t) => t.teamSlug)).not.toContain('outbound');
    // Headline is the measured channel only — no invented Outbound score.
    expect(dive.headline.score).toBe(80);
    expect(dive.headline.measuredAgentsCount).toBe(1);
    expect(dive.headline.supportPositionsCount).toBe(0);
    // No support positions, KPIs, or actions were measured for this scope.
    expect(dive.supportPositions).toEqual([]);
    expect(dive.keyKpis).toEqual([]);
    expect(dive.actionsByPosition.items).toEqual([]);
    expect(dive.actionsByPosition.totalExpectedLiftPct).toBe(0);
    expect(dive.actionsByPosition.projectedNextMonthScore).toBe(dive.headline.score);
    // The only agent needing attention is the real measured agent.
    expect(dive.agentsNeedingAttention).toHaveLength(1);
    expect(dive.agentsNeedingAttention[0].agentName).toBe('Inbound Agent');
  });

  it('EGY single-channel dive omits the missing Outbound card instead of showing the September baseline', () => {
    const records: ExecRecord[] = [
      makeRecord('inb1', 'Inbound Agent', 'Inbound', 'EGY', '2026-09', 'September', 2026, 80),
      makeRecord('inb1', 'Inbound Agent', 'Inbound', 'EGY', '2026-10', 'October', 2026, 80),
    ];
    const dive = buildCallCenterDeepDiveFromRecords(records, [], 'EGY', '2026-10');

    expect(dive.agentTeams).toHaveLength(1);
    expect(dive.agentTeams[0].teamSlug).toBe('inbound');
    expect(dive.headline.score).toBe(80);
    expect(dive.supportPositions).toEqual([]);
    expect(dive.keyKpis).toEqual([]);
    expect(dive.actionsByPosition.items).toEqual([]);
    // No September baseline names or scores leak into the attention list.
    expect(dive.agentsNeedingAttention.map((a) => a.agentName)).toEqual(['Inbound Agent']);
    expect(dive.headline.narrative).not.toContain('Trainer is having clear positive impact');
  });

  it('omits support positions when no Call Center position records exist in the effective month', () => {
    const records: ExecRecord[] = [
      ...inboundOutbound('EGY', '2026-10', 'October', 2026, 88, 84),
      ...inboundOutbound('EGY', '2026-09', 'September', 2026, 86, 82),
    ];
    const dive = buildCallCenterDeepDiveFromRecords(records, [], 'EGY', '2026-10');

    expect(dive.supportPositions).toEqual([]);
    expect(dive.headline.supportPositionsCount).toBe(0);
    expect(dive.headline.measuredTeamsCount).toBe(2);
    expect(dive.headline.measuredAgentsCount).toBe(2);
  });

  it('does not carry a support position forward from a stale month', () => {
    const records: ExecRecord[] = [
      ...inboundOutbound('EGY', '2026-10', 'October', 2026, 88, 84),
      makeRecord('tr1', 'Trainer Person', 'Call Center', 'EGY', '2026-09', 'September', 2026, 100, 'Trainer'),
    ];
    const dive = buildCallCenterDeepDiveFromRecords(records, [], 'EGY', '2026-10');

    expect(dive.supportPositions).toEqual([]);
    expect(dive.headline.supportPositionsCount).toBe(0);
  });

  it('leaves a missing intermediate month as a gap and does not invent a change vs previous month', () => {
    const records: ExecRecord[] = [
      ...inboundOutbound('EGY', '2026-08', 'August', 2026, 85, 80),
      ...inboundOutbound('EGY', '2026-10', 'October', 2026, 90, 86),
    ];
    const dive = buildCallCenterDeepDiveFromRecords(records, [], 'EGY', '2026-10');
    const points = dive.scoreTrend!.points;

    expect(points.find((p) => p.periodKey === '2026-09')?.score).toBeNull();
    expect(dive.scoreTrend?.changeVsPrevious).toBeNull();
    // No invented September-baseline change (the old fallback was +3.3).
    expect(dive.headline.changeVsPrev).toBe(0);
  });

  it('returns a truthful empty state — not the September baseline — when no Call Center rows exist', () => {
    for (const region of ['EGY', 'UAE'] as const) {
      const dive = buildCallCenterDeepDiveFromRecords([], [], region, '2026-10');

      expect(dive.isEmpty).toBe(true);
      expect(dive.emptyReason).toContain('No measured Call Center rows');
      expect(dive.agentTeams).toEqual([]);
      expect(dive.supportPositions).toEqual([]);
      expect(dive.keyKpis).toEqual([]);
      expect(dive.agentsNeedingAttention).toEqual([]);
      expect(dive.actionsByPosition.items).toEqual([]);
      expect(dive.headline.measuredAgentsCount).toBe(0);
      expect(dive.headline.measuredTeamsCount).toBe(0);
      expect(dive.headline.supportPositionsCount).toBe(0);
      // The September baseline (90.4) must never stand in for "no data".
      expect(dive.headline.score).not.toBe(90.4);
      expect(dive.headline.narrative).toContain('No measured rows');
    }
  });

  it('emptyMeasuredFunctionDeepDive never presents a snapshot score as a measured score', () => {
    const dive = emptyMeasuredFunctionDeepDive('call-center', 'UAE');
    expect(dive.isEmpty).toBe(true);
    expect(dive.headline.score).toBe(0);
    expect(dive.headline.measuredAgentsCount).toBe(0);
    expect(dive.agentTeams).toEqual([]);
    expect(dive.supportPositions).toEqual([]);
    expect(dive.keyKpis).toEqual([]);
  });

  it('explicit preview may stand in the September snapshot, but only when nothing was measured at all', () => {
    // The September 2026 presentation demo: no records, preview opted in.
    const preview = buildCallCenterDeepDiveFromRecords(
      [],
      [],
      'EGY',
      '2026-09',
      { allowSnapshotFallback: true },
    );
    expect(preview.isEmpty).not.toBe(true);
    expect(preview.headline.score).toBe(90.4);
    expect(preview.monthLabel).toBe('September 2026');

    // The same opt-in never rescues a measured month: a missing channel
    // in a measured dive stays missing.
    const measured = buildCallCenterDeepDiveFromRecords(
      [
        makeRecord('inb1', 'Inbound Agent', 'Inbound', 'EGY', '2026-10', 'October', 2026, 80),
      ],
      [],
      'EGY',
      '2026-10',
      { allowSnapshotFallback: true },
    );
    expect(measured.headline.score).toBe(80);
    expect(measured.agentTeams.map((team) => team.teamSlug)).toEqual(['inbound']);

    // And there is no September Call Center snapshot for UAE to stand in.
    const uaePreview = buildCallCenterDeepDiveFromRecords(
      [],
      [],
      'UAE',
      '2026-09',
      { allowSnapshotFallback: true },
    );
    expect(uaePreview.isEmpty).toBe(true);
    expect(uaePreview.headline.score).toBe(0);
  });
});

describe('Call Center Deep Dive view — empty states', () => {
  it('renders a truthful empty state instead of a score when there is no measured data', () => {
    const dive = buildCallCenterDeepDiveFromRecords([], [], 'UAE', '2026-10');
    render(
      <CallCenterDeepDiveView
        data={dive}
        onBackToOverview={vi.fn()}
        onSelectAgentTeam={vi.fn()}
      />,
    );

    expect(screen.getByTestId('deep-dive-empty-state')).toBeInTheDocument();
    expect(screen.getByTestId('agent-teams-empty')).toBeInTheDocument();
    expect(screen.getByTestId('support-positions-empty')).toBeInTheDocument();
    expect(screen.getByTestId('key-kpis-empty')).toBeInTheDocument();
    expect(screen.getByTestId('actions-empty')).toBeInTheDocument();
    // No invented September names or scores on the page.
    expect(screen.queryByText(/Hagar Ahmed Amin Diab/)).not.toBeInTheDocument();
    expect(screen.queryByTestId('deep-dive-function-score')).not.toBeInTheDocument();
  });

  it('renders per-section empty states for a single-channel dive', () => {
    const records: ExecRecord[] = [
      makeRecord('inb1', 'Inbound Agent', 'Inbound', 'UAE', '2026-10', 'October', 2026, 80),
    ];
    const dive = buildCallCenterDeepDiveFromRecords(records, [], 'UAE', '2026-10');
    render(
      <CallCenterDeepDiveView
        data={dive}
        onBackToOverview={vi.fn()}
        onSelectAgentTeam={vi.fn()}
      />,
    );

    expect(screen.queryByTestId('deep-dive-empty-state')).not.toBeInTheDocument();
    expect(screen.getByTestId('deep-dive-function-score')).toHaveTextContent('80.0%');
    expect(screen.getByTestId('support-positions-empty')).toBeInTheDocument();
    expect(screen.getByTestId('key-kpis-empty')).toBeInTheDocument();
    expect(screen.getByTestId('actions-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('agent-team-card-outbound-agents')).not.toBeInTheDocument();
  });
});
