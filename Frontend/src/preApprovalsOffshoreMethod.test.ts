import { describe, expect, it } from 'vitest';
import { getKPIsForAgent, type AgentRecord } from './types';

const counts = {
  AssignedRequest: '100',
  ApprovedRequests: '90',
  RejectedRequests: '5',
  PolicyRej: '2',
  ApprovalWithin48HR: '85',
  SubmittedClaims: '200',
  ErrosClaims: '2',
};

function offshoreAgent(raw: Record<string, string>): AgentRecord {
  return {
    identity: { name: 'Test Agent', month: 'June', team: 'Pre-Approvals IP Offshore' },
    raw_data: raw,
    calls: { inbound: 0, outbound: 0, total_handled: 0, abandoned: 0, aht_raw: '00:00:00' },
    geo: { bookings: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 }, attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 } },
    actual: {},
    achievement: {},
    evaluation: { score: 0, grade: 'E' },
    kpi_values: [],
  } as unknown as AgentRecord;
}

describe('Pre-Approvals IP Offshore KPI cards by method', () => {
  it('shows the controllable rejection rate and fixed 1% target for rows scored by the June 2026 method', () => {
    const kpis = getKPIsForAgent(offshoreAgent({
      ...counts,
      ScoringMethod: 'preapprovals_offshore_v2',
      ControllableRejectionRate: '0.03',
      'T.Rejection%': '0.05',
    }));

    const rejection = kpis.find((kpi) => kpi.key === 'Rejection');
    expect(rejection?.label).toBe('Controllable Rejection Rate');
    expect(rejection?.actual).toBeCloseTo(0.03);
    expect(rejection?.target).toBeCloseTo(0.01);
    expect(kpis.find((kpi) => kpi.key === 'Submission')?.target).toBeCloseTo(0.9);
  });

  it('keeps all rejections and the workbook target for earlier rows without the marker', () => {
    const kpis = getKPIsForAgent(offshoreAgent({ ...counts, 'T.Rejection%': '0.03' }));

    const rejection = kpis.find((kpi) => kpi.key === 'Rejection');
    expect(rejection?.label).toBe('Rejection Rate');
    expect(rejection?.actual).toBeCloseTo(0.05);
    expect(rejection?.target).toBeCloseTo(0.03);
  });
});
