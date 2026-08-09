import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { AgentRecord } from '../../types';
import { getKPIsForAgent } from '../../types';
import KpiBreakdownPanel from './KpiBreakdownPanel';

const marketingAgent = {
  identity: {
    name: 'Marketing Employee',
    employee_id: 'SGHD70001',
    team: 'Marketing',
    month: 'June',
  },
  calls: { inbound: 0, outbound: 0, total_handled: 0, abandoned: 0, aht_raw: '00:00:00' },
  geo: {
    bookings: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
    attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
  },
  actual: { booking_rate: 0, attend_rate: 0, abandon_rate: 0 },
  achievement: { booking_ach: 0, attend_ach: 0 },
  evaluation: { score: 51.1, grade: 'E' },
  kpi_values: [
    {
      kpi_key: 'cpl',
      label: 'CPL',
      unit: 'AED',
      direction: 'lower_better',
      actual_value: 136,
      target_value: 60,
      achievement_ratio: 0.441,
      weight_applied: 0.1,
      contribution: 0.0441,
    },
    {
      kpi_key: 'app_installs',
      label: 'App Installs',
      unit: 'count',
      direction: 'higher_better',
      actual_value: 0,
      target_value: 0,
      achievement_ratio: 0,
      weight_applied: 0.1,
      contribution: 0,
    },
  ],
} as AgentRecord;

const preApprovalsAgent = {
  identity: {
    name: 'Sandhya Dhanesh Chandran',
    employee_id: 'SGHD03715',
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
  calls: { inbound: 0, outbound: 0, total_handled: 0, abandoned: 0, aht_raw: '00:00:00' },
  geo: { bookings: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 }, attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 } },
  actual: { booking_rate: 0, attend_rate: 0, abandon_rate: 0 },
  achievement: { booking_ach: 0, attend_ach: 0 },
  evaluation: { score: 0.016, grade: 'E' },
  kpi_values: [
    { kpi_key: 'combined_acceptance_rate', label: 'combined_acceptance_rate', unit: '%', direction: 'higher_better', actual_value: 1, target_value: 1, achievement_ratio: 1, weight_applied: 0.5, contribution: 0.5 },
    { kpi_key: 'er_initial_rejection_rate', label: 'ER Initial Rejection %', unit: '%', direction: 'lower_better', actual_value: 0.0588, target_value: 0.03, achievement_ratio: 0.51, weight_applied: 0.6, contribution: 0.306 },
    { kpi_key: 'approval_within_1_5_hours', label: 'Approval Within 1.5 Hours %', unit: '%', direction: 'higher_better', actual_value: 0.9333, target_value: 1, achievement_ratio: 0.9333, weight_applied: 0.4, contribution: 0.3733 },
  ],
} as AgentRecord;

describe('KpiBreakdownPanel', () => {
  it('normalizes stored KPI ratios for profile display', () => {
    const [cpl] = getKPIsForAgent(marketingAgent);
    expect(cpl.achievement).toBeCloseTo(44.1);
    expect(cpl.weight).toBe(0.1);
    expect(cpl.contribution).toBeCloseTo(4.41);

    render(<KpiBreakdownPanel score={51.1} agent={marketingAgent} teamWeights={{}} />);

    const cplCard = screen.getByText('CPL').closest('div.rounded-xl');
    expect(cplCard).not.toBeNull();
    expect(within(cplCard as HTMLElement).getByText('44.1%')).toBeInTheDocument();
    expect(within(cplCard as HTMLElement).getByText('4.4%')).toBeInTheDocument();
    expect(within(cplCard as HTMLElement).getByText('10%')).toBeInTheDocument();
  });

  it('marks a zero target for review instead of treating it as achieved', () => {
    render(<KpiBreakdownPanel score={51.1} agent={marketingAgent} teamWeights={{}} />);

    expect(screen.getByText(/Review App Installs Target/)).toBeInTheDocument();
    const installsCard = screen.getByText('App Installs').closest('div.rounded-xl');
    expect(installsCard).not.toBeNull();
    expect(within(installsCard as HTMLElement).getByText('—')).toBeInTheDocument();
    expect(within(installsCard as HTMLElement).getByText('0.0%')).toBeInTheDocument();
  });

  it('shows only the selected workstream KPIs and recalculates the final score', () => {
    render(<KpiBreakdownPanel score={1.6} agent={preApprovalsAgent} teamWeights={{}} />);

    expect(screen.getByText('ER / IP Approval')).toBeInTheDocument();
    expect(screen.getByText('Performance Score')).toBeInTheDocument();
    expect(screen.getByText('67.9%')).toBeInTheDocument();
    expect(screen.getByText('ER Initial Rejection %')).toBeInTheDocument();
    expect(screen.getByText('Approval Within 1.5 Hours %')).toBeInTheDocument();
    expect(screen.queryByText('combined_acceptance_rate')).not.toBeInTheDocument();
  });
});
