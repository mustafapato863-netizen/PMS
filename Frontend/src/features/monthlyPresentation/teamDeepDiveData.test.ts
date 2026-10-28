import { describe, expect, it } from 'vitest';
import type { ExecRecord } from '../executive/compose';
import { CALL_CENTER_DEEP_DIVE_SEP_2026, HUMAN_RESOURCES_DEEP_DIVE_SEP_2026, RCM_DEEP_DIVE_SEP_2026 } from './callCenterDeepDiveData';
import { buildRoleDetail, noteFields } from './roleDetailData';
import { buildTeamDeepDiveFromRecords } from './teamDeepDiveData';

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
