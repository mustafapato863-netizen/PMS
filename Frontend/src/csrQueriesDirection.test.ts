import { describe, expect, it } from 'vitest';
import { getKPIsForAgent, type AgentRecord } from './types';

const csrAgent = {
  identity: { name: 'CSR Agent', month: 'June', team: 'CSR' },
  raw_data: {
    'A.CSRRejection%': '4', 'T.CSRRejection%': '5',
    'A.CSRQueries': '120', 'T.QueriesTarget': '100',
    'A.CPTConversion%': '30', 'T.AttendedC.R': '35',
    Rejection_Achievement: '100', Queries_Achievement: '100', AttendedCR_Achievement: '85',
  },
  calls: { inbound: 0, outbound: 0, total_handled: 0, abandoned: 0, aht_raw: '00:00:00' },
  geo: { bookings: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 }, attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 } },
  actual: { booking_rate: 0, attend_rate: 0, abandon_rate: 0 },
  achievement: { booking_ach: 0, attend_ach: 0 },
  evaluation: { score: 0.9, grade: 'B' },
} as unknown as AgentRecord;

describe('legacy CSR KPI cards', () => {
  it('treats Queries Handled as higher-is-better and keeps Rejection lower-is-better', () => {
    const kpis = getKPIsForAgent(csrAgent);
    expect(kpis.find((kpi) => kpi.label === 'Queries Handled')?.isLowerBetter).toBeFalsy();
    expect(kpis.find((kpi) => kpi.label === 'Rejection')?.isLowerBetter).toBe(true);
  });
});
