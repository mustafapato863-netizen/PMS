import { describe, expect, it } from 'vitest';
import type { AgentRecord, TeamAgentRow } from '../../types';
import { isHossamRecord } from '../../types';
import { calculateAggregatedTeamPerformance } from './teamKpiAggregator';
import type { TeamConfig } from '../../schemas/teamConfig.schema';
import { composeExecutiveSummary } from '../executive/compose';
import type { ExecRecord } from '../executive/compose';

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
});
