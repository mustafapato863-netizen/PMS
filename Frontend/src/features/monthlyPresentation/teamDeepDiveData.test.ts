import { describe, expect, it } from 'vitest';
import { toExecRecords, type ExecRecord } from '../executive/compose';
import type { AgentRecord } from '../../types';
import type { TeamConfig } from '../../schemas/teamConfig.schema';
import {
  CALL_CENTER_DEEP_DIVE_SEP_2026,
  HUMAN_RESOURCES_DEEP_DIVE_SEP_2026,
  RCM_DEEP_DIVE_SEP_2026,
  buildFunctionDeepDiveFromRecords,
} from './callCenterDeepDiveData';
import { buildRoleDetail, noteFields } from './roleDetailData';
import { applyTeamTrendConfig, buildTeamDeepDiveFromRecords, selectedTeamConfigSource, unavailableTeamTrend } from './teamDeepDiveData';
import {
  EGYPT_RESUBMISSION_TEAM_CONFIG,
  INBOUND_TEAM_CONFIG,
  UAE_RESUBMISSION_TEAM_CONFIG,
} from './callCenterTeamConfigs';
import { calculateAggregatedTeamPerformance, displayedTeamScore, recordsUseAppliedPin } from '../team/teamKpiAggregator';

const september = { year: 2026, month: 'September', key: '2026-09' };

describe('saved action notes', () => {
  it('preserves decimal values in expected impact', () => {
    expect(noteFields('Owner: Team Lead. Status: Open. Expected impact: +2.5% role score lift.')).toEqual({
      owner: 'Team Lead', status: 'Open', expectedImpact: '+2.5% role score lift',
    });
  });
});

function kpi(
  key: string,
  label: string,
  actual: number,
  target: number,
  direction: 'higher_better' | 'lower_better',
  ratio: number,
): ExecRecord['kpis'][number] {
  return {
    kpi_key: key,
    label,
    unit: 'percent',
    direction,
    actual_value: actual,
    target_value: target,
    achievement_ratio: ratio,
    weight_applied: 0.4,
    contribution: 1,
  };
}

function person(employeeId: string, name: string, score: number, kpis: ExecRecord['kpis']): ExecRecord {
  return {
    employeeId,
    name,
    team: 'Pre-Approvals IP',
    region: 'EGY',
    position: 'Specialist',
    level: 'Employee',
    branches: [],
    period: september,
    score,
    kpis,
  };
}

describe('generic team deep dive agent KPIs', () => {
  it('shows each measured KPI on the agent row instead of a dash', () => {
    const dive = buildTeamDeepDiveFromRecords('pre-approvals-ip', [
      person('ali', 'Ali Mohamed', 74.8, [
        kpi('error', 'Error %', 2.1, 5, 'lower_better', 0.4),
        kpi('approval', 'Approval within 48 hrs', 70.4, 90, 'higher_better', 0.78),
      ]),
      person('hadeer', 'Hadeer Gamal', 86.5, [
        kpi('error', 'Error %', 0.4, 5, 'lower_better', 1),
        kpi('approval', 'Approval within 48 hrs', 59.6, 90, 'higher_better', 0.66),
      ]),
    ], [], 'EGY', '2026-09');

    const ali = dive.agentsAverageOrBelow.find((agent) => agent.employeeId === 'ali');
    const hadeer = dive.agentsAverageOrBelow.find((agent) => agent.employeeId === 'hadeer');
    expect(ali?.kpiCells.map((cell) => cell.actualFormatted)).toEqual(['2.1%', '70.4%']);
    expect(hadeer?.kpiCells.map((cell) => cell.actualFormatted)).toEqual(['0.4%', '59.6%']);
    expect(ali?.kpiCells.find((cell) => cell.kpiKey === 'error')?.metTarget).toBe(true);
    expect(hadeer?.kpiCells.find((cell) => cell.kpiKey === 'approval')?.metTarget).toBe(false);

    const error = dive.kpis.find((item) => item.kpiKey === 'error');
    const approval = dive.kpis.find((item) => item.kpiKey === 'approval');
    expect(error?.agentsMeetingTarget).toBe(2);
    expect(approval?.agentsMeetingTarget).toBe(0);
  });

  it('uses the leader scorecard for Key Team KPIs when that scorecard is the team total', () => {
    const august = { year: 2026, month: 'August', key: '2026-08' };
    const july = { year: 2026, month: 'July', key: '2026-07' };
    const hossam = person('SGHD70094', 'Hossam Mohamed Abdelsameea Tolba Ahmed', 88.61, [
      kpi('error', 'Error %', 1, 5, 'lower_better', 0.9),
      kpi('approval', '% Approval within 48 hrs', 95, 90, 'higher_better', 1),
      kpi('rejection', 'IP Initial Rejection %', 1.2, 2, 'lower_better', 0.8),
      { ...kpi('rejection_all', 'IP Initial Rejection %(All)', 9.9, 2, 'lower_better', 0.1), weight_applied: 0 },
    ]);
    hossam.position = 'Pre-Authorization Supervisor';
    hossam.level = 'Managerial';
    const ali = person('ali', 'Ali Mohamed', 74.8, [
      kpi('error', 'Error %', 4, 5, 'lower_better', 0.4),
      kpi('approval', '% Approval within 48 hrs', 70, 90, 'higher_better', 0.78),
      kpi('rejection', 'IP Initial Rejection %', 4, 2, 'lower_better', 0.4),
    ]);
    const hadeer = person('hadeer', 'Hadeer Gamal', 80, [
      kpi('error', 'Error %', 7, 5, 'lower_better', 0.2),
      kpi('approval', '% Approval within 48 hrs', 60, 90, 'higher_better', 0.66),
      kpi('rejection', 'IP Initial Rejection %', 6.8, 2, 'lower_better', 0.2),
    ]);
    const hossamAugust = {
      ...hossam,
      period: august,
      score: 86,
      kpis: [
        kpi('error', 'Error %', 2.4, 5, 'lower_better', 0.7),
        kpi('approval', '% Approval within 48 hrs', 91, 90, 'higher_better', 1),
        kpi('rejection', 'IP Initial Rejection %', 1.8, 2, 'lower_better', 0.7),
      ],
    };
    const aliAugust = {
      ...ali,
      period: august,
      kpis: [kpi('error', 'Error %', 8, 5, 'lower_better', 0.2)],
    };
    const aliJuly = {
      ...ali,
      period: july,
      kpis: [kpi('error', 'Error %', 3, 5, 'lower_better', 0.5)],
    };
    const hadeerJuly = {
      ...hadeer,
      period: july,
      kpis: [kpi('error', 'Error %', 5, 5, 'lower_better', 0.5)],
    };
    const dubaiLow = person('dubai-low', 'Dubai Low', 70, [
      kpi('error', 'Error %', 2, 5, 'lower_better', 0.8),
    ]);
    dubaiLow.team = 'Pre-Approvals OP Dubai';
    const dubaiHigh = person('dubai-high', 'Dubai High', 90, [
      kpi('error', 'Error %', 6, 5, 'lower_better', 0.4),
    ]);
    dubaiHigh.team = 'Pre-Approvals OP Dubai';

    const records = [hossam, ali, hadeer, hossamAugust, aliAugust, aliJuly, hadeerJuly, dubaiLow, dubaiHigh];
    const dive = buildTeamDeepDiveFromRecords('pre-approvals-ip', records, [], 'EGY', '2026-09');
    const card = (key: string) => dive.kpis.find((item) => item.kpiKey === key);

    expect(dive.summary.score).toBe(88.6);
    expect(dive.kpis.map((item) => item.kpiKey).sort()).toEqual(['approval', 'error', 'rejection']);
    expect(card('error')?.actualFormatted).toBe('1.0%');
    expect(card('error')?.targetFormatted).toBe('5.0%');
    expect(card('error')?.achievementPct).toBe(90);
    expect(card('error')?.movementFormatted).toBe('-1.4%');
    expect(card('approval')?.actualFormatted).toBe('95.0%');
    expect(card('approval')?.achievementPct).toBe(100);
    expect(card('rejection')?.actualFormatted).toBe('1.2%');
    expect(card('rejection')?.achievementPct).toBe(80);
    expect(card('error')?.agentsMeetingTarget).toBe(2);
    expect(card('error')?.totalAgents).toBe(3);
    expect(card('error')?.trend6Mo.find((point) => point.periodKey === '2026-09')?.actualFormatted).toBe('1.0%');
    expect(card('error')?.trend6Mo.find((point) => point.periodKey === '2026-08')?.actualFormatted).toBe('2.4%');
    expect(card('error')?.trend6Mo.find((point) => point.periodKey === '2026-07')?.actualFormatted).toBe('4.0%');

    const aliRow = dive.agentsAverageOrBelow.find((agent) => agent.employeeId === 'ali');
    const hadeerRow = dive.agentsAverageOrBelow.find((agent) => agent.employeeId === 'hadeer');
    expect(aliRow?.kpiCells.find((cell) => cell.kpiKey === 'error')?.actualFormatted).toBe('4.0%');
    expect(aliRow?.kpiCells.find((cell) => cell.kpiKey === 'error')?.metTarget).toBe(true);
    expect(hadeerRow?.kpiCells.find((cell) => cell.kpiKey === 'error')?.actualFormatted).toBe('7.0%');
    expect(hadeerRow?.kpiCells.find((cell) => cell.kpiKey === 'error')?.metTarget).toBe(false);
    expect(hadeerRow?.kpiCells.find((cell) => cell.kpiKey === 'approval')?.actualFormatted).toBe('60.0%');

    const dubai = buildTeamDeepDiveFromRecords('pre-approvals-op-dubai', records, [], 'EGY', '2026-09');
    expect(dubai.summary.score).toBe(80);
    expect(dubai.kpis.find((item) => item.kpiKey === 'error')?.actualFormatted).toBe('4.0%');
  });

  it('shows Submission EGY actuals on Salma when her KPI keys differ from the column key', () => {
    const salma = person('Salma Nagy Ali Hendy', 'Salma Nagy Ali Hendy', 71.6, [
      kpi('egy_submission_initial_rejection', 'Initial Rejection %', 3.8, 2, 'lower_better', 0.526),
      kpi('egy_submission_due_date', '% of Submission Within Due date', 99.9, 90, 'higher_better', 1),
    ]);
    salma.team = 'Submission EGY';
    salma.position = 'Claim & Audit Specialist';
    const colleague = person('SGHD80001', 'Colleague Missing Due Date', 80, [
      kpi('submission_initial_rejection', 'Initial Rejection %', 8, 2, 'lower_better', 0.25),
      kpi('egy_coding_quality_errors', 'Coding Errors %', 11.3, 5, 'lower_better', 0.442),
    ]);
    colleague.team = 'Submission EGY';
    colleague.position = 'Claim & Audit Specialist';

    const records = [salma, colleague];
    const dive = buildTeamDeepDiveFromRecords('submission-egy', records, [], 'EGY', '2026-09');
    const salmaRow = dive.agentsAverageOrBelow.find((agent) => agent.agentName === 'Salma Nagy Ali Hendy');
    const colleagueRow = dive.agentsAverageOrBelow.find((agent) => agent.employeeId === 'SGHD80001');
    const labeled = (row: { kpiCells?: { label: string; actualFormatted: string }[] } | undefined, label: string) =>
      row?.kpiCells?.filter((cell) => cell.label.trim().toLowerCase() === label.toLowerCase()) ?? [];

    expect(salmaRow?.score).toBe(71.6);
    expect(labeled(salmaRow, 'Initial Rejection %').map((cell) => cell.actualFormatted)).toEqual(['3.8%', '3.8%']);
    expect(labeled(salmaRow, '% of Submission Within Due date').map((cell) => cell.actualFormatted)).toEqual(['99.9%']);
    expect(labeled(salmaRow, 'Coding Errors %').map((cell) => cell.actualFormatted)).toEqual(['—']);
    expect(labeled(colleagueRow, '% of Submission Within Due date').map((cell) => cell.actualFormatted)).toEqual(['—']);
    expect(labeled(colleagueRow, 'Initial Rejection %').every((cell) => cell.actualFormatted === '8.0%')).toBe(true);
    expect(labeled(colleagueRow, 'Coding Errors %').map((cell) => cell.actualFormatted)).toEqual(['11.3%']);

    const role = buildRoleDetail(RCM_DEEP_DIVE_SEP_2026, 'claim-and-audit-specialist', [], records);
    const salmaMember = role.members.find((member) => member.personName === 'Salma Nagy Ali Hendy');
    const colleagueMember = role.members.find((member) => member.employeeId === 'SGHD80001');
    expect(salmaMember?.score).toBe(71.6);
    expect(labeled(salmaMember, 'Initial Rejection %').map((cell) => cell.actualFormatted)).toEqual(['3.8%', '3.8%']);
    expect(labeled(salmaMember, '% of Submission Within Due date').map((cell) => cell.actualFormatted)).toEqual(['99.9%']);
    expect(labeled(salmaMember, 'Coding Errors %').map((cell) => cell.actualFormatted)).toEqual(['—']);
    expect(labeled(colleagueMember, '% of Submission Within Due date').map((cell) => cell.actualFormatted)).toEqual(['—']);
  });

  it('uses the September Submission EGY baseline measurements instead of dashes', () => {
    const dive = buildTeamDeepDiveFromRecords('submission-egy', [], [], 'EGY', '2026-09');
    const salma = dive.agentsAverageOrBelow.find((agent) => agent.agentName === 'Salma Nagy Ali Hendy');
    expect(salma?.score).toBe(71.6);
    const rejection = salma?.kpiCells.find((cell) => /initial rejection/i.test(cell.label));
    expect(rejection?.actualFormatted).toBe('3.8%');
    const dueDate = salma?.kpiCells.find((cell) => /submission/i.test(cell.label) && /due/i.test(cell.label));
    if (dueDate) expect(dueDate.actualFormatted).toBe('99.9%');
    const unrelated = salma?.kpiCells.find((cell) => /coding errors/i.test(cell.label));
    expect(unrelated?.actualFormatted).toBe('—');
  });

  it('does not backfill fake KPI trend values for months before a person started', () => {
    const august = { year: 2026, month: 'August', key: '2026-08' };
    const diaaAug: ExecRecord = {
      ...person('diaa', 'Mohamed Diaa Eldin Youssef', 100, [
        kpi('assess_quality', 'Assessment Quality Score', 100, 100, 'higher_better', 1),
      ]),
      team: 'Human Resources',
      position: 'Assessment Center Lead',
      period: august,
    };
    const diaaSep: ExecRecord = {
      ...diaaAug,
      period: september,
    };

    const role = buildRoleDetail(
      HUMAN_RESOURCES_DEEP_DIVE_SEP_2026,
      'assessment-center-lead',
      [],
      [diaaAug, diaaSep],
    );
    const qualityKpi = role.kpis.find((item) => item.kpiKey === 'assess_quality');
    expect(qualityKpi).toBeDefined();
    expect(qualityKpi?.trend6Mo.map((pt) => pt.actual)).toEqual([
      null,
      null,
      null,
      null,
      100,
      100,
    ]);
    expect(qualityKpi?.trend6Mo.slice(0, 4).every((pt) => pt.actualFormatted === '—')).toBe(true);
    expect(qualityKpi?.trend6Mo.slice(0, 4).every((pt) => pt.metTarget === null)).toBe(true);
    expect(qualityKpi?.structuralDiagnosis).toContain('2 of 2 measured months');
  });

  it('separates multi-holder support roles (Team Leader) into individual members with actual performance', () => {
    const role = buildRoleDetail(CALL_CENTER_DEEP_DIVE_SEP_2026, 'team-leader', [], []);
    expect(role.roleTitle).toBe('Team Leader');
    expect(role.headcount).toBe(2);
    expect(role.below90Count).toBe(1);
    expect(role.score).toBe(89.8);
    expect(role.grade).toBe('C');
    expect(role.gradeFullLabel).toBe('Average');

    // Both individuals exist separately
    expect(role.members).toHaveLength(2);

    const amr = role.members.find((m) => /amr badawy/i.test(m.personName));
    expect(amr).toBeDefined();
    expect(amr?.score).toBe(86.3);
    expect(amr?.grade).toBe('C');
    expect(amr?.gradeFullLabel).toBe('Average');
    expect(amr?.keyKpiLabel).toBe('Reachability');
    expect(amr?.keyKpiActual).toBe('53.0%');
    expect(amr?.kpiCells?.find((c) => /booking/i.test(c.label))?.actualFormatted).toBe('—');
    expect(amr?.kpiCells?.find((c) => /quality/i.test(c.label))?.metTarget).toBeNull();

    const adham = role.members.find((m) => /adham sameh/i.test(m.personName));
    expect(adham).toBeDefined();
    expect(adham?.score).toBe(93.4);
    expect(adham?.grade).toBe('B');
    expect(adham?.gradeFullLabel).toBe('Meet Expectations');
    expect(adham?.kpiCells?.find((c) => /booking/i.test(c.label))?.actualFormatted).toBe('—');
    expect(adham?.kpiCells?.find((c) => /aht/i.test(c.label))?.actualFormatted).toBe('—');
    expect(adham?.kpiCells?.find((c) => /quality/i.test(c.label))?.metTarget).toBeNull();

    // Individual action plan focuses on the member requiring action (Amr Badawy Mohamed)
    const amrAction = role.individualActionPlans.find((p) => /amr badawy/i.test(p.personName));
    expect(amrAction).toBeDefined();
    expect(amrAction?.score).toBe(86.3);
    expect(amrAction?.gradeFullLabel).toBe('Average');
    expect(amrAction?.suggested).toBe(true);
    expect(amrAction?.expectedImpact).toBe('Impact to be confirmed');
    expect(role.actions.every((action) => !action.suggested || (action.dueDate === null && action.expectedImpact === 'Impact to be confirmed'))).toBe(true);
  });

  it('combines Inbound Team Leader and Outbound Team Leader records into the single Team Leader role detail', () => {
    const amrRecord: ExecRecord = {
      ...person('amr-1', 'Amr Badawy Mohamed', 86.29, [
        kpi('pos_outbound_team_leader_booking_cr', 'Booking CR%', 30.5, 30.0, 'higher_better', 1.0),
        kpi('pos_outbound_team_leader_attended_cr', 'Attended CR%', 56.2, 65.0, 'higher_better', 0.86),
        kpi('pos_outbound_team_leader_reachability', 'Reachability %', 53.0, 75.0, 'higher_better', 0.71),
        kpi('pos_outbound_team_leader_quality_score', 'Quality Score', 96.0, 95.0, 'higher_better', 1.0),
      ]),
      team: 'Call Center',
      position: 'Outbound Team Leader',
    };

    const adhamRecord: ExecRecord = {
      ...person('adham-1', 'Adham Sameh Abdallah Arafa', 93.39, [
        kpi('pos_inbound_team_leader_booking_cr', 'Booking CR%', 62.0, 65.0, 'higher_better', 0.95),
        kpi('pos_inbound_team_leader_attended_cr', 'Attended CR%', 68.5, 75.0, 'higher_better', 0.91),
        kpi('pos_inbound_team_leader_aht', 'AHT', 2.73, 2.5, 'lower_better', 0.91),
        kpi('pos_inbound_team_leader_quality_score', 'Quality Score', 98.4, 95.0, 'higher_better', 1.0),
      ]),
      team: 'Call Center',
      position: 'Inbound Team Leader',
    };

    const role = buildRoleDetail(CALL_CENTER_DEEP_DIVE_SEP_2026, 'team-leader', [], [amrRecord, adhamRecord]);
    expect(role.roleTitle).toBe('Team Leader');
    expect(role.headcount).toBe(2);
    expect(role.below90Count).toBe(1);

    const amrMember = role.members.find((m) => m.employeeId === 'amr-1');
    expect(amrMember).toBeDefined();
    expect(amrMember?.score).toBe(86.3);

    const adhamMember = role.members.find((m) => m.employeeId === 'adham-1');
    expect(adhamMember).toBeDefined();
    expect(adhamMember?.score).toBe(93.4);
  });
});

describe('team score trend', () => {
  const months = [
    { key: '2026-04', month: 'April', score: 50 },
    { key: '2026-05', month: 'May', score: 60 },
    { key: '2026-06', month: 'June', score: 70 },
    { key: '2026-07', month: 'July', score: 80 },
    { key: '2026-08', month: 'August', score: 90 },
    { key: '2026-09', month: 'September', score: 100 },
  ];

  function scored(team: string, region: 'EGY' | 'UAE', key: string, month: string, score: number, kpis = [kpi('quality', 'Quality', score, 100, 'higher_better', score / 100)]): ExecRecord {
    return {
      ...person(`${team}-${key}`, team, score, kpis),
      team,
      region,
      period: { year: 2026, month, key },
    };
  }

  it('uses six calendar months and keeps the latest point equal to the team score', () => {
    const records = months.map((item) => scored('Coding EGY', 'EGY', item.key, item.month, item.score));
    const dive = buildTeamDeepDiveFromRecords('coding', records, [], 'EGY', '2026-09');

    expect(dive.scoreTrend?.points.map((point) => point.score)).toEqual([50, 60, 70, 80, 90, 100]);
    expect(dive.scoreTrend?.points.filter((point) => point.selected).map((point) => point.score)).toEqual([dive.summary.score]);
    expect(dive.summary.scoreLabel).toBeUndefined();
    expect(dive.scoreTrend?.changeVsPrevious).toBe(10);
    expect(dive.scoreTrend?.basisNote).toBeNull();
  });

  it.each([
    ['coding', 'Coding EGY', 'EGY', 'quality_errors', 'Quality Errors Rate'],
    ['inbound', 'Inbound', 'EGY', 'booking', 'Booking Rate'],
    ['outbound', 'Outbound', 'EGY', 'booking', 'Booking Rate'],
    ['coding', 'Coding', 'UAE', 'quality_errors', 'Quality Errors Rate'],
  ] as const)('uses recorded months for both KPI trend and score movement: %s %s', (slug, team, region, key, label) => {
    const records = [
      scored(team, region, '2026-08', 'August', 70, [kpi(key, label, 40, 100, 'higher_better', 0.4)]),
      scored(team, region, '2026-09', 'September', 80, [kpi(key, label, 60, 100, 'higher_better', 0.6)]),
    ];
    const dive = buildTeamDeepDiveFromRecords(slug, records, [], region, '2026-09');
    const trend = dive.kpis.find((item) => item.kpiKey === key)?.trend6Mo;
    expect(trend?.map((point) => point.actual)).toEqual([null, null, null, null, 40, 60]);
    const scorePoints = dive.scoreTrend!.points;
    expect(dive.scoreTrend?.changeVsPrevious).toBeCloseTo(scorePoints[5].score! - scorePoints[4].score!, 1);
  });

  it.each([
    ['coding', 'Coding EGY', 'quality_errors', 'Quality Errors Rate'],
    ['inbound', 'Inbound', 'booking', 'Booking Rate'],
  ] as const)('does not compare a KPI to an earlier month when the previous month is missing: %s', (slug, team, key, label) => {
    const records = [
      scored(team, 'EGY', '2026-07', 'July', 70, [kpi(key, label, 40, 100, 'higher_better', 0.4)]),
      scored(team, 'EGY', '2026-09', 'September', 80, [kpi(key, label, 60, 100, 'higher_better', 0.6)]),
    ];
    const dive = buildTeamDeepDiveFromRecords(slug, records, [], 'EGY', '2026-09');
    expect(dive.kpis.find((item) => item.kpiKey === key)?.movementFormatted).toBe('—');
    expect(dive.scoreTrend?.changeVsPrevious).toBeNull();
  });

  it('leaves missing months empty and compares only the previous calendar month', () => {
    const records = [
      scored('Coding EGY', 'EGY', '2026-07', 'July', 80),
      scored('Coding EGY', 'EGY', '2026-09', 'September', 100),
    ];
    const dive = buildTeamDeepDiveFromRecords('coding', records, [], 'EGY', '2026-09');

    expect(dive.scoreTrend?.points.map((point) => point.score)).toEqual([null, null, null, 80, null, 100]);
    expect(dive.scoreTrend?.points.some((point) => point.score === 0)).toBe(false);
    expect(dive.scoreTrend?.changeVsPrevious).toBeNull();
    expect(dive.summary.score).toBe(100);
  });

  it('keeps the requested month when records exist only in other months', () => {
    for (const team of ['Coding EGY', 'Inbound']) {
      const dive = buildTeamDeepDiveFromRecords(team, [scored(team, 'EGY', '2026-08', 'August', 80)], [], 'EGY', '2026-09');
      expect(dive.periodKey).toBe('2026-09');
      expect(dive.monthLabel).toBe('September 2026');
      expect(dive.summary.scoreLabel).toBe('Unmeasured team score');
      for (const result of [unavailableTeamTrend(dive), applyTeamTrendConfig(dive, { ...INBOUND_TEAM_CONFIG, team, db_name: team })]) {
        expect(result.scoreTrend?.points.at(-1)).toMatchObject({ periodKey: '2026-09', score: null, selected: true });
        expect(result.scoreTrend?.changeVsPrevious).toBeNull();
        expect(result.summary.scoreLabel).toBe('Unmeasured team score');
      }
    }
  });

  it('applies the Egypt Resubmission configuration to both Egypt aliases and rejects UAE config on Egypt records', () => {
    const records = [scored('Resubmission', 'EGY', '2026-09', 'September', 80), scored('Re-Submission EGY', 'EGY', '2026-09', 'September', 90)];
    const dive = buildTeamDeepDiveFromRecords('re-submission', records, [], 'EGY', '2026-09');
    expect(dive.scoringRecords).toHaveLength(2);
    expect(selectedTeamConfigSource(dive)).toBe('Resubmission');
    expect(dive.summary.score).toBe(85);
    expect(dive.scoreTrend?.points.at(-1)?.score).toBe(85);
    const uaeRejected = applyTeamTrendConfig(dive, UAE_RESUBMISSION_TEAM_CONFIG);
    expect(uaeRejected.scoreTrend?.points.at(-1)).toMatchObject({ score: null, basisDetail: 'Scoring basis unavailable' });
    expect(uaeRejected.summary.scoreLabel).toMatch(/unavailable/);
  });

  it('keeps a short history inside the six-month window', () => {
    const records = [
      scored('Coding EGY', 'EGY', '2026-08', 'August', 40),
      scored('Coding EGY', 'EGY', '2026-09', 'September', 55),
    ];
    const dive = buildTeamDeepDiveFromRecords('coding', records, [], 'EGY', '2026-09');

    expect(dive.scoreTrend?.points).toHaveLength(6);
    expect(dive.scoreTrend?.points.map((point) => point.score)).toEqual([null, null, null, null, 40, 55]);
    expect(dive.scoreTrend?.changeVsPrevious).toBe(15);
  });

  it('does not mix Egypt and UAE or two teams, and follows the selected month', () => {
    const records = [
      ...months.map((item) => scored('Coding EGY', 'EGY', item.key, item.month, item.score)),
      scored('Coding', 'UAE', '2026-09', 'September', 20),
      scored('Submission EGY', 'EGY', '2026-09', 'September', 33),
    ];
    const egypt = buildTeamDeepDiveFromRecords('coding', records, [], 'EGY', '2026-09');
    const uae = buildTeamDeepDiveFromRecords('coding', records, [], 'UAE', '2026-09');
    const submission = buildTeamDeepDiveFromRecords('submission', records, [], 'EGY', '2026-09');

    expect(egypt.scoreTrend?.points.at(-1)?.score).toBe(100);
    expect(egypt.summary.score).toBe(100);
    expect(uae.summary.score).toBe(20);
    expect(uae.scoreTrend?.points.map((point) => point.score)).toEqual([null, null, null, null, null, 20]);
    expect(submission.summary.score).toBe(33);
    expect(submission.scoreTrend?.points.at(-1)?.score).toBe(33);

    const august = buildTeamDeepDiveFromRecords('coding', records, [], 'EGY', '2026-08');
    expect(august.periodKey).toBe('2026-08');
    expect(august.summary.score).toBe(90);
    expect(august.scoreTrend?.points.find((point) => point.selected)?.score).toBe(90);
    expect(august.scoreTrend?.points.at(-1)?.month).toBe('Aug');
  });

  it('does not copy a sample baseline into the measured trend', () => {
    const dive = buildTeamDeepDiveFromRecords('submission-egy', [], [], 'EGY', '2026-09');

    expect(dive.summary.scoreLabel).toBe('Sample team score');
    expect(dive.scoreTrend?.points).toHaveLength(6);
    expect(dive.scoreTrend?.points.every((point) => point.score === null)).toBe(true);
    expect(dive.scoreTrend?.changeVsPrevious).toBeNull();
    expect(dive.summary.score).not.toBe(0);
  });
  it('provides six empty measured months for call center previews', () => {
    for (const team of ['inbound', 'outbound']) {
      const dive = buildTeamDeepDiveFromRecords(team, [], [], 'EGY', '2026-09');
      expect(dive.summary.scoreLabel).toBe('Sample team score');
      expect(dive.scoreTrend?.points).toHaveLength(6);
      expect(dive.scoreTrend?.points.every((point) => point.score === null)).toBe(true);
      expect(dive.scoreTrend?.points.at(-1)?.periodKey).toBe(dive.periodKey);
    }
  });
  it('uses dashboard pooling with applied historical targets and flags unknown historical rules', () => {
    const config: TeamConfig = {
      team: 'Support', db_name: 'Support', region: 'EGY', employee_id_col: 'ID', employee_name_col: 'Name',
      grade_thresholds: { A: 95, B: 85, C: 75, D: 65 },
      kpis: [{ key: 'Resolution', label: 'Resolution Rate', weight: 1, direction: 'higher_better', unit: '%', color: '#000', actual_col: 'Resolved', target_col: 'Total', score_target: 1, score_formula: 'target_ratio', cap_achievement: true, aggregation: { method: 'ratio', numerator_col: 'Resolved', denominator_col: 'Total' } }],
    };
    const agent = (id: string, month: string, resolved: number, total: number, target: number, team = 'Support') => ({
      identity: { employee_id: id, name: id, team, month }, region: 'EGY', year: 2026, performance_level: 'Employee',
      raw_data: { Resolved: String(resolved), Total: String(total) },
      evaluation: { score: resolved / total, grade: 'C' },
      kpi_values: [{ kpi_key: 'Resolution', label: 'Resolution Rate', actual_value: resolved / total, target_value: target, unit: '%', direction: 'higher_better', weight_applied: month === 'August' ? 0.4 : 1, achievement_ratio: resolved / total, contribution: resolved / total, evaluation_pinned: true }],
    } as unknown as AgentRecord);
    const records = toExecRecords([agent('a', 'August', 10, 20, 0.9), agent('b', 'August', 80, 80, 0.9), agent('a', 'September', 10, 20, 1), agent('b', 'September', 80, 80, 1)]);
    const initial = buildTeamDeepDiveFromRecords('support', records, [], 'EGY', '2026-09');
    expect(unavailableTeamTrend(initial).scoreTrend?.points.at(-1)?.score).toBeNull();
    const result = applyTeamTrendConfig(initial, config);
    expect(result.scoreTrend?.points.slice(-2).map((point) => point.score)).toEqual([40, 90]);
    expect(result.summary.score).toBe(90);
    expect(result.scoreTrend?.changeVsPrevious).toBe(50);
    expect(result.scoreTrend?.points.at(-2)?.basisDetail).toMatch(/saved targets and weights; current pooling rules/i);
    expect(result.scoreTrend?.points.at(-1)?.basisDetail).toMatch(/current pooling rules/);
    const legacy = toExecRecords([agent('a', 'August', 10, 20, 0.9), agent('b', 'August', 80, 80, 0.9), agent('a', 'September', 10, 20, 1), agent('b', 'September', 80, 80, 1)]);
    legacy[0].rawAgent!.kpi_values![0].evaluation_pinned = false;
    const incomplete = applyTeamTrendConfig(buildTeamDeepDiveFromRecords('support', legacy, [], 'EGY', '2026-09'), config);
    expect(incomplete.scoreTrend?.points.at(-2)?.basisDetail).toMatch(/Some weighted KPIs use saved settings.*not verified/);
    expect(incomplete.scoreTrend?.basisNote).toBeNull();
    const unpinned = toExecRecords([agent('a', 'August', 10, 20, 0.9), agent('a', 'September', 10, 20, 1)]);
    unpinned.forEach((record) => { record.rawAgent!.kpi_values![0].evaluation_pinned = false; });
    const unknown = applyTeamTrendConfig(buildTeamDeepDiveFromRecords('support', unpinned, [], 'EGY', '2026-09'), config);
    expect(unknown.scoreTrend?.points.at(-2)?.basisDetail).toMatch(/Historical settings are not verified.*stored or workbook values/);
    expect(unknown.scoreTrend?.basisNote).toBeNull();
    const wrongConfig = applyTeamTrendConfig(initial, { ...config, team: 'Other', db_name: 'Other' });
    expect(wrongConfig.scoreTrend?.points.at(-1)?.score).toBeNull();

    const aliasConfig = { ...config, team: 'Resubmission', db_name: 'Resubmission', aliases: ['Re-Submission EGY'] };
    const aliases = toExecRecords([
      agent('a', 'August', 10, 20, 0.9, 'Re-Submission EGY'),
      agent('b', 'August', 80, 80, 0.9, 'Resubmission'),
      agent('a', 'September', 10, 20, 1, 'Resubmission'),
      agent('b', 'September', 80, 80, 1, 'Resubmission'),
      agent('a', 'July', 10, 20, 1, 'Re-Submission EGY'),
      agent('a', 'June', 10, 20, 1, 'Resubmission'),
    ]);
    const aliasDive = buildTeamDeepDiveFromRecords('re-submission', aliases, [], 'EGY', '2026-09');
    expect(selectedTeamConfigSource(aliasDive)).toBe('Resubmission');
    const aliasResult = applyTeamTrendConfig(aliasDive, aliasConfig);
    expect(aliasResult.scoreTrend?.points.slice(-4).map((point) => point.score)).toEqual([50, 50, 40, 90]);
    expect(aliasResult.scoreTrend?.points.at(-2)?.basisDetail).toMatch(/saved targets and weights; current pooling rules/i);
    expect(aliasResult.scoreTrend?.points.at(-3)?.basisDetail).toMatch(/saved targets and weights; current pooling rules/i);
    expect(aliasResult.summary.score).toBe(90);
    expect(aliasResult.scoreTrend?.changeVsPrevious).toBe(50);
    expect(aliasResult.scoreTrend?.basisNote).toMatch(/evaluation settings/i);

    const mixedSelected = buildTeamDeepDiveFromRecords('re-submission', [
      ...aliases,
      ...toExecRecords([agent('c', 'September', 70, 100, 1, 'Re-Submission EGY')]),
    ], [], 'EGY', '2026-09');
    expect(selectedTeamConfigSource(mixedSelected)).toBe('Resubmission');
    expect(applyTeamTrendConfig(mixedSelected, aliasConfig).scoreTrend?.points.at(-1)?.score).toBe(80);

    // Unconfirmed multi-source teams must still report unavailable scoring basis when mixed
    const unconfirmedMix = buildTeamDeepDiveFromRecords('pre-approvals-ip', [
      ...toExecRecords([agent('a', 'September', 10, 20, 1, 'Pre-Approvals IP')]),
      { ...toExecRecords([agent('b', 'September', 80, 80, 1, 'Pre-Approvals IP Offshore')])[0], team: 'Pre-Approvals IP Offshore' },
    ], [], 'EGY', '2026-09');
    unconfirmedMix.scoringRecords = [
      ...toExecRecords([agent('a', 'September', 10, 20, 1, 'Pre-Approvals IP')]),
      ...toExecRecords([agent('b', 'September', 80, 80, 1, 'Pre-Approvals IP Offshore')]),
    ];
    expect(selectedTeamConfigSource(unconfirmedMix)).toBe('');
    expect(applyTeamTrendConfig(unconfirmedMix, { ...config, team: 'Pre-Approvals IP', db_name: 'Pre-Approvals IP' }).scoreTrend?.points.at(-1)?.score).toBeNull();
  });

  it('scores Egypt Re-Submission aliases separately and together, deduplicates duplicate employee records, and keeps UAE Re-Submission separate', () => {
    const egyAgent = (
      id: string,
      team: 'Resubmission' | 'Re-Submission EGY',
      month: string,
      qualityActual: number,
      tatActual: number,
      qualityTarget = 0.05,
      qualityWeight = 0.5,
      tatWeight = 0.5,
      pinned = true,
    ): AgentRecord => {
      const qAch = Math.min(1, qualityTarget / qualityActual);
      const tAch = Math.min(1, tatActual / 1.0);
      const score = qAch * qualityWeight + tAch * tatWeight;
      return {
        identity: { employee_id: id, name: `Analyst ${id}`, team, month, position: 'Resubmission Analyst' },
        region: 'EGY',
        year: 2026,
        position: 'Resubmission Analyst',
        performance_level: 'Employee',
        raw_data: {},
        evaluation: { score, grade: 'C' },
        kpi_values: [
          {
            kpi_key: 'egy_resubmission_quality_errors',
            label: 'Quality Errors Rate',
            actual_value: qualityActual,
            target_value: qualityTarget,
            unit: '%',
            direction: 'lower_better',
            weight_applied: qualityWeight,
            achievement_ratio: qAch,
            contribution: qAch * qualityWeight,
            evaluation_pinned: pinned,
          },
          {
            kpi_key: 'egy_resubmission_rejection',
            label: 'Rejection Rate After Re-Submission',
            actual_value: 0,
            target_value: 0.6,
            unit: '%',
            direction: 'lower_better',
            weight_applied: 0,
            achievement_ratio: 1,
            contribution: 0,
            evaluation_pinned: pinned,
            view_only: true,
          },
          {
            kpi_key: 'egy_resubmission_tat',
            label: 'TAT',
            actual_value: tatActual,
            target_value: 1.0,
            unit: '%',
            direction: 'higher_better',
            weight_applied: tatWeight,
            achievement_ratio: tAch,
            contribution: tAch * tatWeight,
            evaluation_pinned: pinned,
          },
        ],
      } as unknown as AgentRecord;
    };

    const uaeAgent = (id: string, month: string): AgentRecord => ({
      identity: { employee_id: id, name: `UAE ${id}`, team: 'Re-Submission', month },
      region: 'UAE',
      year: 2026,
      performance_level: 'Employee',
      raw_data: {
        'FinalErrorsClaims(RaisedbyQualitySameMonth)': '1',
        QltySamples: '50',
        'A.QualityErrorsRate': '0.02',
        'T.QualityErrorsRate': '0.05',
        'RejectedClaims3MonthsPrevious(byInsurance)': '5',
        RemittanceAmount: '100',
        'A.RejectionRateAfterRe-Submission': '0.05',
        'T.RejectionRateAfterRe-Submission': '0.10',
        'TotalSubmittedWithin(TAT)': '95',
        Allocatedclaims: '100',
        'A.TAT': '0.95',
        'T.TAT': '0.90',
      },
      evaluation: { score: 0.96, grade: 'A' },
      kpi_values: [
        {
          kpi_key: 'quality_errors_rate',
          label: 'Quality Errors Rate',
          actual_value: 0.02,
          target_value: 0.05,
          unit: '%',
          direction: 'lower_better',
          weight_applied: 0.2,
          achievement_ratio: 1,
          contribution: 0.2,
          evaluation_pinned: true,
        },
        {
          kpi_key: 'rejection_rate_after_resubmission',
          label: 'Rejection Rate After Re-Submission',
          actual_value: 0.05,
          target_value: 0.1,
          unit: '%',
          direction: 'lower_better',
          weight_applied: 0.5,
          achievement_ratio: 1,
          contribution: 0.5,
          evaluation_pinned: true,
        },
        {
          kpi_key: 'tat',
          label: 'TAT compliance %',
          actual_value: 0.95,
          target_value: 0.9,
          unit: '%',
          direction: 'higher_better',
          weight_applied: 0.3,
          achievement_ratio: 1,
          contribution: 0.3,
          evaluation_pinned: true,
        },
      ],
    } as unknown as AgentRecord);

    // 1. Each Egypt alias separately (June: Resubmission only; July: Re-Submission EGY only)
    // 2. Missing month (May has no records -> null gap)
    // 3. Both aliases in the same month (September) + duplicate employee record for SGHD70104
    const rawAgents: AgentRecord[] = [
      egyAgent('SGHD70104', 'Resubmission', 'April', 0.05, 0.80, 0.05, 0.5, 0.5, false), // unpinned historical month -> 90.0%
      // May is missing -> null gap
      egyAgent('SGHD70104', 'Resubmission', 'June', 0.05, 0.90), // Resubmission only -> 95.0%
      egyAgent('SGHD70104', 'Re-Submission EGY', 'July', 0.05, 0.86), // Re-Submission EGY only -> 93.0%
      egyAgent('SGHD70104', 'Re-Submission EGY', 'August', 0.10, 0.80, 0.08, 0.4, 0.6), // historical target 0.08 & weight 0.4/0.6 -> (0.8*0.4 + 0.8*0.6)=80.0%
      egyAgent('SGHD70104', 'Resubmission', 'September', 0.10, 0.80), // 0.5*0.5 + 0.8*0.5 = 65.0%
      egyAgent('SGHD70105', 'Re-Submission EGY', 'September', 0.05, 1.00), // second employee under alias -> 100.0%
      uaeAgent('UAE9001', 'September'),
    ];

    // The API has already resolved conflicting alias rows using upload evidence.
    const execRecords = toExecRecords(rawAgents);
    const egyptDive = buildTeamDeepDiveFromRecords('re-submission', execRecords, [], 'EGY', '2026-09');
    const configuredEgypt = applyTeamTrendConfig(egyptDive, EGYPT_RESUBMISSION_TEAM_CONFIG);
    const fnDiveEgypt = buildFunctionDeepDiveFromRecords('rcm', execRecords, [], 'EGY', '2026-09');
    const fnCardEgypt = fnDiveEgypt.agentTeams.find((t) => t.teamSlug === 're-submission');

    // Deduplicated headcount in September is 2 (SGHD70104 + SGHD70105), not 3
    expect(configuredEgypt.summary.headcount).toBe(2);
    expect(fnCardEgypt?.headcount).toBe(2);
    expect(fnCardEgypt?.teamName).toBe('Re-Submission');

    // Dashboard pooled score for September across SGHD70104 (quality 0.10, tat 0.80) and SGHD70105 (quality 0.05, tat 1.00):
    // Average quality actual = 0.075 vs target 0.05 -> achievement 0.05 / 0.075 = 66.6667% * 0.5 = 33.3333%
    // Average TAT actual = 0.90 vs target 1.00 -> achievement 90.0% * 0.5 = 45.0%
    // Pooled score = 78.3%
    const sepDedupedAgents = [
      egyAgent('SGHD70104', 'Resubmission', 'September', 0.10, 0.80),
      egyAgent('SGHD70105', 'Re-Submission EGY', 'September', 0.05, 1.00),
    ];
    const dashboardPooled = calculateAggregatedTeamPerformance(sepDedupedAgents, EGYPT_RESUBMISSION_TEAM_CONFIG);
    const dashboardScore = Math.round(
      displayedTeamScore(
        dashboardPooled?.score ?? null,
        (65 + 100) / 2,
        recordsUseAppliedPin(sepDedupedAgents),
      ) * 10,
    ) / 10;

    expect(dashboardScore).toBe(78.3);
    // Agreement across Function Deep Dive card, Team Deep Dive card, 6-month trend selected point, and Team Dashboard
    expect(configuredEgypt.summary.score).toBe(dashboardScore);
    expect(egyptDive.summary.score).toBe(dashboardScore);
    expect(fnCardEgypt?.score).toBe(dashboardScore);
    expect(configuredEgypt.scoreTrend?.points.find((p) => p.selected)?.score).toBe(dashboardScore);

    // 6-month trend: Apr (90), May (null gap), Jun (95), Jul (93), Aug (80), Sep (78.3)
    expect(configuredEgypt.scoreTrend?.points.map((p) => p.score)).toEqual([90, null, 95, 93, 80, 78.3]);
    expect(configuredEgypt.scoreTrend?.points[0]?.basisDetail).toBe(
      'Historical settings are not verified. The score may use stored or workbook values and current pooling rules.',
    );
    expect(configuredEgypt.scoreTrend?.points[1]?.basisDetail).toBeUndefined();
    expect(configuredEgypt.scoreTrend?.points[4]?.basisDetail).toBe(
      'Available weighted KPIs use saved targets and weights; current pooling rules.',
    );
    expect(configuredEgypt.scoreTrend?. basisNote).toMatch(/evaluation settings/i);

    // UAE Re-Submission stays separate with its own config and 100% score
    const uaeDive = buildTeamDeepDiveFromRecords('re-submission', execRecords, [], 'UAE', '2026-09');
    const configuredUae = applyTeamTrendConfig(uaeDive, UAE_RESUBMISSION_TEAM_CONFIG);
    expect(configuredUae.summary.headcount).toBe(1);
    expect(configuredUae.summary.score).toBe(100);
    expect(configuredUae.scoreTrend?.points.map((p) => p.score)).toEqual([null, null, null, null, null, 100]);

    // Legacy slugs ('resubmission' and 're-submission-egy') resolve the same Egypt records
    const legacyResub = buildTeamDeepDiveFromRecords('resubmission', execRecords, [], 'EGY', '2026-09');
    const legacyResubEgy = buildTeamDeepDiveFromRecords('re-submission-egy', execRecords, [], 'EGY', '2026-09');
    expect(legacyResub.summary.score).toBe(dashboardScore);
    expect(legacyResubEgy.summary.score).toBe(dashboardScore);
  });
  it('marks a comparison when the scoring weight changed', () => {
    const light = [{ ...kpi('quality', 'Quality', 80, 100, 'higher_better', 0.8), evaluation_pinned: true, weight_applied: 0.4 }];
    const heavy = [{ ...kpi('quality', 'Quality', 90, 100, 'higher_better', 0.9), evaluation_pinned: true, weight_applied: 0.7 }];
    const dive = buildTeamDeepDiveFromRecords('coding', [
      scored('Coding EGY', 'EGY', '2026-08', 'August', 80, light),
      scored('Coding EGY', 'EGY', '2026-09', 'September', 90, heavy),
    ], [], 'EGY', '2026-09');

    expect(dive.scoreTrend?.changeVsPrevious).toBe(10);
    expect(dive.scoreTrend?.basisNote).toMatch(/evaluation settings/i);
    expect(dive.scoreTrend?.points.find((point) => point.selected)?.score).toBe(dive.summary.score);
  });
});
