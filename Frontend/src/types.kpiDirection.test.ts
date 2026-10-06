import { describe, expect, it } from 'vitest';
import type { AgentRecord } from './types';
import { getKPIsForAgent } from './types';

const csrLegacyAgent = {
  identity: { name: 'CSR Employee', employee_id: 'SGHD80001', team: 'CSR', month: 'June' },
  raw_data: {
    'A.CSRRejection%': '2',
    'T.CSRRejection%': '3',
    'A.CSRQueries': '90',
    'T.QueriesTarget': '100',
    'A.CPTConversion%': '40',
    'T.AttendedC.R': '50',
  },
  calls: { inbound: 0, outbound: 0, total_handled: 0, abandoned: 0, aht_raw: '00:00:00' },
  geo: {
    bookings: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
    attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
  },
  actual: { booking_rate: 0, attend_rate: 0, abandon_rate: 0 },
  achievement: { booking_ach: 0, attend_ach: 0 },
  evaluation: { score: 80, grade: 'C' },
} as AgentRecord;

describe('legacy CSR KPI direction', () => {
  it('treats Queries Handled as higher-is-better, matching the CSR config', () => {
    const kpis = getKPIsForAgent(csrLegacyAgent);
    const queries = kpis.find((kpi) => kpi.label === 'Queries Handled');
    const rejection = kpis.find((kpi) => kpi.label === 'Rejection');

    expect(queries).toBeDefined();
    expect(queries?.isLowerBetter).toBeFalsy();
    expect(rejection?.isLowerBetter).toBe(true);
  });
});
