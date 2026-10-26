import { describe, expect, it } from 'vitest';
import type { AgentRecord, TeamAgentRow } from '../../types';
import { isHossamRecord } from '../../types';
import { calculateAggregatedTeamPerformance } from './teamKpiAggregator';
import type { TeamConfig } from '../../schemas/teamConfig.schema';
import { composeExecutiveSummary } from '../executive/compose';
import type { ExecRecord } from '../executive/compose';
import { buildTeamDeepDiveFromRecords } from '../monthlyPresentation/teamDeepDiveData';

const PRE_APPROVALS_CONFIG: TeamConfig = {
  team: 'Pre-Approvals IP',
  db_name: 'Pre-Approvals IP',
  region: 'EGY',
  employee_id_col: 'Employee ID',
  employee_name_col: 'Employee Name',
  grade_thresholds: { A: 95, B: 90, C: 80, D: 70 },
  performance_levels: {
    Employee: {
      positions: {
        'Pre-Authorization Specialist': {
          kpis: [
            { key: 'pa_initial_rejection', label: 'IP Initial Rejection %', weight: 0.3, direction: 'lower_better', unit: '%', color: '#DC2626', actual_col: 'Actual Value', target_col: 'Target Value', aggregation: { method: 'average' }, display_order: 1 },
            { key: 'pa_error_rate', label: 'Error %', weight: 0.3, direction: 'lower_better', unit: '%', color: '#D97706', actual_col: 'Actual Value', target_col: 'Target Value', aggregation: { method: 'average' }, display_order: 2 },
            { key: 'pa_approval_48h', label: '% Approval within 48 hrs', weight: 0.4, direction: 'higher_better', unit: '%', color: '#0D9488', actual_col: 'Actual Value', target_col: 'Target Value', aggregation: { method: 'average' }, display_order: 3 },
          ],
        },
      },
    },
    Managerial: {
      positions: {
        'Pre-Authorization Supervisor': {
          kpis: [
            { key: 'pa_initial_rejection', label: 'IP Initial Rejection %', weight: 0.5, direction: 'lower_better', unit: '%', color: '#DC2626', actual_col: 'Actual Value', target_col: 'Target Value', aggregation: { method: 'average' }, display_order: 1 },
            { key: 'pa_initial_rejection_all', label: 'IP Initial Rejection %(All)', weight: 0, direction: 'lower_better', unit: '%', color: '#7C3AED', actual_col: 'Actual Value', target_col: 'Target Value', aggregation: { method: 'average' }, display_order: 2, view_only: true },
            { key: 'pa_error_rate', label: 'Error %', weight: 0.2, direction: 'lower_better', unit: '%', color: '#D97706', actual_col: 'Actual Value', target_col: 'Target Value', aggregation: { method: 'average' }, display_order: 3 },
            { key: 'pa_approval_48h', label: '% Approval within 48 hrs', weight: 0.3, direction: 'higher_better', unit: '%', color: '#0D9488', actual_col: 'Actual Value', target_col: 'Target Value', aggregation: { method: 'average' }, display_order: 4 },
          ],
        },
      },
    },
  },
  kpis: [],
};

const createSpecialist = (id: string, name: string, score: number): AgentRecord => ({
  identity: { employee_id: id, name, team: 'Pre-Approvals IP', month: 'September', position: 'Pre-Authorization Specialist' },
  performance_level: 'Employee',
  score,
  evaluation: { score },
  kpi_values: [],
  calls: { total: 0, aht_raw: '' },
  region: 'EGY',
  year: 2026,
});

const createHossam = (score = 88.61): AgentRecord => ({
  identity: {
    employee_id: 'SGHD70094',
    name: 'Hossam Mohamed Abdelsameea Tolba Ahmed',
    team: 'Pre-Approvals IP',
    month: 'September',
    position: 'Pre-Authorization Supervisor',
  },
  performance_level: 'Managerial',
  score,
  evaluation: { score },
  kpi_values: [
    { kpi_key: 'pa_initial_rejection', label: 'IP Initial Rejection %', actual_value: 0.0, target_value: 0.01, weight_applied: 0.5, achievement_ratio: 1.0, direction: 'lower_better', unit: '%' },
    { kpi_key: 'pa_error_rate', label: 'Error %', actual_value: 0.01, target_value: 0.01, weight_applied: 0.2, achievement_ratio: 1.0, direction: 'lower_better', unit: '%' },
    { kpi_key: 'pa_approval_48h', label: '% Approval within 48 hrs', actual_value: 0.96, target_value: 0.9, weight_applied: 0.3, achievement_ratio: 1.0667, direction: 'higher_better', unit: '%' },
  ],
  calls: { total: 0, aht_raw: '' },
  region: 'EGY',
  year: 2026,
});

describe('Pre-Approvals team scoring with Hossam supervisor scorecard', () => {
  it('correctly identifies Hossam Mohamed record by employee ID, name or position', () => {
    expect(isHossamRecord(createHossam())).toBe(true);
    expect(isHossamRecord({ employee_id: 'SGHD70094' })).toBe(true);
    expect(isHossamRecord({ employee_id: '70094' })).toBe(true);
    expect(isHossamRecord({ name: 'Hossam Mohamed' })).toBe(true);
    expect(isHossamRecord({ position: 'Pre-Authorization Supervisor' })).toBe(true);
    expect(isHossamRecord(createSpecialist('SGHD70134', 'Salma', 78))).toBe(false);
  });

  it('calculateAggregatedTeamPerformance returns Hossam supervisor score as the canonical team score', () => {
    const specialist1 = createSpecialist('SGHD70099', 'Manar', 83.2);
    const specialist2 = createSpecialist('SGHD70143', 'Nouran', 76.78);
    const hossam = createHossam(88.61);

    const result = calculateAggregatedTeamPerformance([specialist1, specialist2, hossam], PRE_APPROVALS_CONFIG);
    expect(result).not.toBeNull();
    // Hossam's score is 88.61, not the arithmetic average of (83.2 + 76.78 + 88.61)/3 = 82.86
    expect(result?.score).toBe(88.61);
  });

  it('composeExecutiveSummary assigns Hossam supervisor score to Pre-Approvals IP team in Function/Executive view', () => {
    const hossamRecord: ExecRecord = {
      employeeId: 'SGHD70094',
      name: 'Hossam Mohamed',
      team: 'Pre-Approvals IP',
      region: 'EGY',
      position: 'Pre-Authorization Supervisor',
      level: 'Managerial',
      period: { key: '2026-09', year: 2026, month: 'September' },
      score: 88.61,
      kpis: [],
      rawAgent: createHossam(88.61),
    };
    const specialistRecord: ExecRecord = {
      employeeId: 'SGHD70143',
      name: 'Nouran',
      team: 'Pre-Approvals IP',
      region: 'EGY',
      position: 'Pre-Authorization Specialist',
      level: 'Employee',
      period: { key: '2026-09', year: 2026, month: 'September' },
      score: 76.78,
      kpis: [],
      rawAgent: createSpecialist('SGHD70143', 'Nouran', 76.78),
    };

    const summary = composeExecutiveSummary({
      view: 'function',
      functionName: 'RCM',
      role: 'Admin',
      filters: {},
      records: [hossamRecord, specialistRecord],
      today: new Date(2026, 8, 30),
      teamConfigs: [PRE_APPROVALS_CONFIG],
    });

    const preApprovalsTeam = summary.teams.find((t) => t.team === 'Pre-Approvals IP');
    expect(preApprovalsTeam).toBeDefined();
    // The team score must be Hossam's score (88.6%), not Nouran's 76.8% or average 82.7%
    expect(preApprovalsTeam?.score).toBe(88.6);
    expect(preApprovalsTeam?.grade).toBe('C');
  });

  it('keeps the leader team total when the employee slice is averaged later, and leaves Coding, Pre-Approvals OP Dubai, and Pre-Approvals IP Offshore on their own averages', () => {
    const september = { key: '2026-09', year: 2026, month: 'September' };
    const specialistScores = [80, 82, 84, 85];
    const specialistKpis: AgentRecord['kpi_values'] = [
      { kpi_key: 'pa_initial_rejection', label: 'IP Initial Rejection %', actual_value: 1.207729, target_value: 1, weight_applied: 0.3, achievement_ratio: 0.828, direction: 'lower_better', unit: '%', contribution: 24.84 },
      { kpi_key: 'pa_error_rate', label: 'Error %', actual_value: 1.207729, target_value: 1, weight_applied: 0.3, achievement_ratio: 0.828, direction: 'lower_better', unit: '%', contribution: 24.84 },
      { kpi_key: 'pa_approval_48h', label: '% Approval within 48 hrs', actual_value: 82.8, target_value: 100, weight_applied: 0.4, achievement_ratio: 0.828, direction: 'higher_better', unit: '%', contribution: 33.12 },
    ];
    const specialists = specialistScores.map((score, index) => {
      const agent = createSpecialist(`SGHD7100${index}`, `Specialist ${index + 1}`, score);
      agent.kpi_values = specialistKpis;
      return agent;
    });
    const hossam = createHossam(88.61);
    const toRecord = (agent: AgentRecord, team: string, region = 'EGY'): ExecRecord => ({
      employeeId: agent.identity.employee_id || agent.identity.name,
      name: agent.identity.name,
      team,
      region,
      position: agent.identity.position ?? null,
      level: agent.performance_level || 'Employee',
      period: september,
      score: Number(agent.evaluation?.score ?? agent.score),
      kpis: [],
      rawAgent: agent,
    });
    const codingLow = createSpecialist('SGHD72001', 'Coding Low', 70);
    codingLow.identity.team = 'Coding EGY';
    codingLow.identity.position = 'Coder';
    const codingHigh = createSpecialist('SGHD72002', 'Coding High', 90);
    codingHigh.identity.team = 'Coding EGY';
    codingHigh.identity.position = 'Coder';
    const dubaiLow = createSpecialist('SGHD73001', 'Dubai Low', 70);
    dubaiLow.identity.team = 'Pre-Approvals OP Dubai';
    dubaiLow.identity.position = 'Pre-Authorization Specialist';
    dubaiLow.region = 'UAE';
    const dubaiHigh = createSpecialist('SGHD73002', 'Dubai High', 90);
    dubaiHigh.identity.team = 'Pre-Approvals OP Dubai';
    dubaiHigh.identity.position = 'Pre-Authorization Specialist';
    dubaiHigh.region = 'UAE';
    const offshoreLow = createSpecialist('SGHD74001', 'Offshore Low', 60);
    offshoreLow.identity.team = 'Pre-Approvals IP Offshore';
    offshoreLow.identity.position = 'Pre-Authorization Specialist';
    const offshoreHigh = createSpecialist('SGHD74002', 'Offshore High', 80);
    offshoreHigh.identity.team = 'Pre-Approvals IP Offshore';
    offshoreHigh.identity.position = 'Pre-Authorization Specialist';

    const records = [
      ...specialists.map((agent) => toRecord(agent, 'Pre-Approvals IP')),
      toRecord(hossam, 'Pre-Approvals IP'),
      toRecord(codingLow, 'Coding EGY'),
      toRecord(codingHigh, 'Coding EGY'),
      toRecord(dubaiLow, 'Pre-Approvals OP Dubai', 'UAE'),
      toRecord(dubaiHigh, 'Pre-Approvals OP Dubai', 'UAE'),
      toRecord(offshoreLow, 'Pre-Approvals IP Offshore'),
      toRecord(offshoreHigh, 'Pre-Approvals IP Offshore'),
    ];
    const summary = composeExecutiveSummary({
      view: 'corporate',
      role: 'Admin',
      filters: { performanceLevel: 'Employee' },
      records,
      today: new Date(2026, 8, 30),
      teamConfigs: [PRE_APPROVALS_CONFIG],
    });

    const preApprovals = summary.teams.find((team) => team.team === 'Pre-Approvals IP');
    const coding = summary.teams.find((team) => team.team === 'Coding EGY');
    const opDubai = summary.teams.find((team) => team.team === 'Pre-Approvals OP Dubai');
    const offshore = summary.teams.find((team) => team.team === 'Pre-Approvals IP Offshore');
    expect(preApprovals?.score).toBe(88.6);
    expect(coding?.score).toBe(80);
    expect(opDubai?.score).toBe(80);
    expect(offshore?.score).toBe(70);
    expect(summary.hero.score).not.toBe(88.6);
    const employeePeople = summary.people.below_90;
    expect(employeePeople.map((person) => [person.name, person.score])).toEqual(
      expect.arrayContaining([
        ['Specialist 1', 80],
        ['Specialist 2', 82],
        ['Specialist 3', 84],
        ['Specialist 4', 85],
      ]),
    );
    expect(employeePeople.some((person) => person.employee_id === 'SGHD70094')).toBe(false);

    const openSlice = composeExecutiveSummary({
      view: 'corporate',
      role: 'Admin',
      filters: {},
      records,
      today: new Date(2026, 8, 30),
      teamConfigs: [PRE_APPROVALS_CONFIG],
    });
    expect(openSlice.teams.find((team) => team.team === 'Pre-Approvals IP')?.score).toBe(88.6);
    expect(openSlice.teams.find((team) => team.team === 'Pre-Approvals OP Dubai')?.score).toBe(80);
    expect(openSlice.teams.find((team) => team.team === 'Pre-Approvals IP Offshore')?.score).toBe(70);

    const managerialDubai = composeExecutiveSummary({
      view: 'managerial',
      team: 'Pre-Approvals OP Dubai',
      role: 'Admin',
      filters: { performanceLevel: 'Employee' },
      records,
      today: new Date(2026, 8, 30),
      teamConfigs: [PRE_APPROVALS_CONFIG],
    });
    expect(managerialDubai.hero.score).toBe(80);
    const managerialIp = composeExecutiveSummary({
      view: 'managerial',
      team: 'Pre-Approvals IP',
      role: 'Admin',
      filters: { performanceLevel: 'Employee' },
      records,
      today: new Date(2026, 8, 30),
      teamConfigs: [PRE_APPROVALS_CONFIG],
    });
    expect(managerialIp.hero.score).toBe(88.6);
    const openPeople = openSlice.people.below_90;
    expect(openPeople.find((person) => person.employee_id === 'SGHD70094')?.score).toBe(88.6);
    expect(openPeople.find((person) => person.name === 'Specialist 1')?.score).toBe(80);
  });

  it('uses the leader total as the Pre-Approvals team-view score and keeps each agent score', () => {
    const september = { key: '2026-09', year: 2026, month: 'September' };
    const people = [
      { employeeId: 'SGHD71000', name: 'Specialist 1', score: 80 },
      { employeeId: 'SGHD71001', name: 'Specialist 2', score: 82 },
      { employeeId: 'SGHD71002', name: 'Specialist 3', score: 84 },
      { employeeId: 'SGHD71003', name: 'Specialist 4', score: 85 },
      { employeeId: 'SGHD70094', name: 'Hossam Mohamed Abdelsameea Tolba Ahmed', score: 88.61 },
    ];
    const records: ExecRecord[] = people.map((person) => ({
      employeeId: person.employeeId,
      name: person.name,
      team: 'Pre-Approvals IP',
      region: 'EGY',
      position: person.employeeId === 'SGHD70094' ? 'Pre-Authorization Supervisor' : 'Pre-Authorization Specialist',
      level: person.employeeId === 'SGHD70094' ? 'Managerial' : 'Employee',
      period: september,
      score: person.score,
      kpis: [],
    }));

    const dive = buildTeamDeepDiveFromRecords('pre-approvals-ip', records, [], 'EGY', '2026-09');
    expect(dive.summary.score).toBe(88.6);
    expect(dive.agentsAverageOrBelow.map((agent) => [agent.employeeId, agent.score])).toEqual([
      ['SGHD71000', 80],
      ['SGHD71001', 82],
      ['SGHD71002', 84],
      ['SGHD71003', 85],
      ['SGHD70094', 88.6],
    ]);
  });
});
