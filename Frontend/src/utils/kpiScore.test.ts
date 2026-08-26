import { describe, expect, it } from 'vitest';
import type { AgentRecord } from '../types';
import { getKPIsForAgent } from '../types';
import { getWeightForLabel, resolveDisplayScore } from './kpiScore';

const record = (month: string, achievement: number, storedScore: number) => ({
  identity: { employee_id: `EMP-${month}`, name: 'Inbound Agent', month, team: 'Inbound' },
  evaluation: { score: storedScore, grade: 'B' },
  calls: { inbound: 0, outbound: 0, total_handled: 0, abandoned: 0, aht_raw: '00:00:00' },
  geo: { bookings: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 }, attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 } },
  actual: { booking_rate: 0, attend_rate: achievement / 100, abandon_rate: 0 },
  achievement: { booking_ach: 0, attend_ach: achievement / 100 },
  kpi_values: [{
    kpi_key: 'Attend', label: 'Attendance Rate', unit: '%', direction: 'higher_better',
    actual_value: achievement / 100, target_value: 1, achievement_ratio: achievement / 100,
    weight_applied: 1, contribution: achievement / 100,
  }],
}) as AgentRecord;

const weightedRecord = (
  team: string,
  month: string,
  achievements: Record<string, number>,
  rawData: Record<string, string> = {},
) => ({
  identity: { employee_id: `EMP-${team}-${month}`, name: `${team} Agent`, month, team },
  evaluation: { score: 0, grade: 'B' },
  calls: { inbound: 0, outbound: 0, total_handled: 0, abandoned: 0, aht_raw: '00:00:00' },
  geo: { bookings: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 }, attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 } },
  actual: { booking_rate: 0, attend_rate: 0, abandon_rate: 0 },
  achievement: { booking_ach: 0, attend_ach: 0 },
  raw_data: rawData,
  kpi_values: Object.entries(achievements).map(([label, achievement]) => ({
    kpi_key: label,
    label,
    unit: '%',
    direction: label.includes('Rejection') || label.includes('Error') ? 'lower_better' as const : 'higher_better' as const,
    actual_value: achievement / 100,
    target_value: 1,
    achievement_ratio: achievement / 100,
    weight_applied: 0,
    contribution: 0,
  })),
}) as AgentRecord;

describe('resolveDisplayScore', () => {
  it('uses the backend score as the single source for every month', () => {
    const weights = { Attend: 1 };
    const may = resolveDisplayScore(record('May', 92.3, 94.4), weights);
    const june = resolveDisplayScore(record('June', 91.3, 0), weights);

    expect(may).toBeCloseTo(94.4);
    expect(june).toBeCloseTo(0);
    expect(june - may).toBeCloseTo(-94.4);
  });

  it('includes Quality in normal Inbound months and applies the June redistribution', () => {
    const weights = { Attend: 0.70, Booking: 0.10, AHT: 0.05, Quality: 0.05, Other: 0.10 };
    const achievements = {
      'Attendance Rate': 100,
      'Booking Rate': 100,
      'AHT (Handle Time)': 100,
      'Quality Score': 50,
      UTZ: 100,
    };

    expect(resolveDisplayScore(weightedRecord('Inbound', 'May', achievements), weights)).toBeCloseTo(0);
    expect(resolveDisplayScore(weightedRecord('Inbound', 'June', achievements), weights)).toBeCloseTo(0);
  });

  it('applies the Pre-Approvals IP Offshore no-claims exception from the same score source', () => {
    const weights = { Rejection: 0.50, InitialError: 0.20, Submission: 0.30 };
    const achievements = {
      'Rejection Rate': 50,
      'Initial Error Rate': 0,
      'Submission Rate': 100,
    };

    const noClaims = weightedRecord('Pre-Approvals IP Offshore', 'June', achievements, { SubmittedClaims: '0' });
    const withClaims = weightedRecord('Pre-Approvals IP Offshore', 'June', achievements, { SubmittedClaims: '10' });

    expect(resolveDisplayScore(noClaims, weights)).toBeCloseTo(0);
    expect(resolveDisplayScore(withClaims, weights)).toBeCloseTo(0);
  });

  it('rebuilds Offshore Initial Error Rate from source counters when persisted KPI values are stale', () => {
    const agent = weightedRecord(
      'Pre-Approvals IP Offshore',
      'July',
      {
        'Rejection Rate': 8.1,
        'Initial Error Rate': 58.7,
        'Submission Rate': 75.2,
      },
      {
        RejectedRequests: '8',
        AssignedRequests: '99',
        ErrosClaims: '3',
        SubmittedClaims: '501',
        ApprovalWithin48HR: '90',
        ApprovedRequests: '120',
        'Error%': '58.7%',
        'T.InitialError%': '2.1%',
      },
    );

    const error = getKPIsForAgent(agent).find((kpi) => kpi.label === 'Initial Error Rate');
    expect(error?.actual).toBeCloseTo(3 / 501, 6);
    expect(error?.target).toBeCloseTo(0.021, 6);
    expect(error?.achievement).toBe(100);
  });

  it('prefers the canonical Offshore rejection target over a stale persisted target', () => {
    const agent = weightedRecord(
      'Pre-Approvals IP Offshore',
      'July',
      { 'Rejection Rate': 8.1, 'Initial Error Rate': 0, 'Submission Rate': 90 },
      {
        RejectedRequests: '2',
        AssignedRequest: '84',
        'T.IPInitialRejection%': '0.03',
      },
    );
    agent.kpi_values![0] = {
      ...agent.kpi_values![0],
      actual_value: 2 / 84,
      target_value: 2 / 84,
    };

    const rejection = getKPIsForAgent(agent).find((kpi) => kpi.label === 'Rejection Rate');
    expect(rejection?.target).toBeCloseTo(0.03, 6);
  });

  it('prefers the canonical Offshore submission target over a stale persisted target', () => {
    const agent = weightedRecord(
      'Pre-Approvals IP Offshore',
      'July',
      { 'Rejection Rate': 8.1, 'Initial Error Rate': 0, 'Submission Rate': 90 },
      {
        ApprovalWithin48HR: '90',
        ApprovedRequests: '100',
        'T.%ofApprovalwithin48hrs': '0.90',
      },
    );
    agent.kpi_values![2] = {
      ...agent.kpi_values![2],
      actual_value: 0.9,
      target_value: 1,
    };

    const submission = getKPIsForAgent(agent).find((kpi) => kpi.label === 'Submission Rate');
    expect(submission?.target).toBeCloseTo(0.90, 6);
  });

  it('rebuilds the new Pre-Approvals workstream score and ignores stale combined KPIs', () => {
    const agent = {
      identity: {
        employee_id: 'SGHD03715',
        name: 'Sandhya Dhanesh Chandran',
        month: 'June',
        team: 'Pre-Approvals IP Elective Dubai',
        position: 'ER / IP Approval',
      },
      raw_data: {
        AssignedRequests: '17',
        ApprovedRequests: '15',
        RejectedRequests: '1',
        'ApprovalWithin1.5HR': '14',
        'T.InitialRejection%': '3%',
        'T.%OfApprovalwithin48HR/1.5HR': '100%',
      },
      evaluation: { score: 0.016, grade: 'E' },
      calls: { inbound: 0, outbound: 0, total_handled: 0, abandoned: 0, aht_raw: '00:00:00' },
      geo: { bookings: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 }, attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 } },
      actual: { booking_rate: 0, attend_rate: 0, abandon_rate: 0 },
      achievement: { booking_ach: 0, attend_ach: 0 },
      kpi_values: [
        { kpi_key: 'combined_acceptance_rate', label: 'combined_acceptance_rate', unit: '%', direction: 'higher_better', actual_value: 1, target_value: 1, achievement_ratio: 1, weight_applied: 0.5, contribution: 0.5 },
        { kpi_key: 'combined_submission_within_month', label: 'combined_submission_within_month', unit: '%', direction: 'higher_better', actual_value: 1, target_value: 1, achievement_ratio: 1, weight_applied: 0.3, contribution: 0.3 },
        { kpi_key: 'er_initial_rejection_rate', label: 'ER Initial Rejection %', unit: '%', direction: 'lower_better', actual_value: 0.0588, target_value: 0.03, achievement_ratio: 0.51, weight_applied: 0.6, contribution: 0.306 },
        { kpi_key: 'approval_within_1_5_hours', label: 'Approval Within 1.5 Hours %', unit: '%', direction: 'higher_better', actual_value: 0.9333, target_value: 1, achievement_ratio: 0.9333, weight_applied: 0.4, contribution: 0.3733 },
      ],
    } as AgentRecord;

    expect(getKPIsForAgent(agent).map((kpi) => kpi.label)).toEqual([
      'ER Initial Rejection %',
      'Approval Within 1.5 Hours %',
    ]);
    expect(resolveDisplayScore(agent, undefined)).toBeCloseTo(67.9, 1);
  });
});

describe('getWeightForLabel', () => {
  it('supports both canonical and legacy attendance weight keys', () => {
    expect(getWeightForLabel({ Attendance: 0.7 }, 'Attendance Rate')).toBe(0.7);
    expect(getWeightForLabel({ Attend: 0.65 }, 'Attendance Rate')).toBe(0.65);
  });

  it('resolves the booking weight used by employee KPI cards', () => {
    expect(getWeightForLabel({ Booking: 0.1 }, 'Booking Rate')).toBe(0.1);
  });
});
