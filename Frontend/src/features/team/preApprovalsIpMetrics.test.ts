import { describe, expect, it } from 'vitest';
import type { AgentRecord } from '../../types';
import { aggregatePreApprovalsIpMetrics } from './preApprovalsIpMetrics';

const record = (
  employeeId: string,
  assigned: number,
  approved: number,
  rejected: number,
  within48Hours: number,
  submittedClaims: number,
  errorsClaims: number,
) => ({
  identity: { employee_id: employeeId, name: employeeId, month: 'June', team: 'Pre-Approvals IP Offshore' },
  evaluation: { score: 0, grade: 'B' },
  calls: { inbound: 0, outbound: 0, total_handled: 0, abandoned: 0, aht_raw: '00:00:00' },
  geo: { bookings: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 }, attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 } },
  actual: {
    booking_rate: 0,
    attend_rate: 0,
    abandon_rate: 0,
    rejection_rate: assigned > 0 ? rejected / assigned : 0,
    initial_error_rate: submittedClaims > 0 ? errorsClaims / submittedClaims : 0,
    submission_rate: approved > 0 ? within48Hours / approved : 0,
  },
  achievement: { booking_ach: 0, attend_ach: 0 },
  raw_data: {
    AssignedRequest: String(assigned),
    ApprovedRequests: String(approved),
    RejectedRequests: String(rejected),
    ApprovalWithin48HR: String(within48Hours),
    SubmittedClaims: String(submittedClaims),
    ErrosClaims: String(errorsClaims),
  },
}) as AgentRecord;

describe('aggregatePreApprovalsIpMetrics', () => {
  it('uses pooled June counters instead of averaging employee rates', () => {
    const agents = [
      record('Salma', 74, 61, 6, 37, 254, 2),
      record('Nouran', 72, 58, 3, 33, 384, 16),
      record('Omar', 74, 55, 5, 38, 280, 10),
      record('Hadeer', 65, 50, 2, 38, 0, 0),
      record('Manar', 120, 110, 10, 109, 0, 0),
    ];

    const result = aggregatePreApprovalsIpMetrics(agents);

    expect(result.rejectionRate).toBeCloseTo((26 / 405) * 100);
    expect(result.errorRate).toBeCloseTo((28 / 918) * 100);
    expect(result.submissionRate).toBeCloseTo((255 / 334) * 100);
    expect(result.rejectionWeight).toBeCloseTo(0.54);
    expect(result.errorWeight).toBeCloseTo(0.12);
    expect(result.submissionWeight).toBeCloseTo(0.34);

    expect(result.rejectionWeight + result.errorWeight + result.submissionWeight).toBeCloseTo(1);
    expect(result.rejectionContribution + result.errorContribution + result.submissionContribution)
      .toBeGreaterThan(0);
  });

  it('falls back to the supplied rates for legacy records without raw counters', () => {
    const legacy = record('Legacy', 10, 8, 1, 7, 20, 1);
    legacy.raw_data = {};

    const result = aggregatePreApprovalsIpMetrics([legacy]);

    expect(result.rejectionRate).toBeCloseTo(10);
    expect(result.errorRate).toBeCloseTo(5);
    expect(result.submissionRate).toBeCloseTo(87.5);
  });
});
