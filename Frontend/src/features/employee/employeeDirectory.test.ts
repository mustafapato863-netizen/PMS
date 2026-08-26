import { describe, expect, it } from 'vitest';
import type { TeamAgentRow } from '../../hooks/usePerformanceData';
import {
  ALL_EMPLOYEE_POSITIONS,
  getEmployeeDirectoryPosition,
  getEmployeeDirectoryPositions,
  getEmployeeDirectoryRows,
  getEmployeeDirectoryTeams,
} from './employeeDirectory';

function row(id: string, name: string, team: string, position?: string): TeamAgentRow {
  return {
    id,
    name,
    team,
    month: 'July',
    performanceLevel: 'Employee',
    score: 80,
    displayWeightedScore: 80,
    gradeClass: 'B',
    gradeLabel: 'B',
    status: 'Meet',
    rootCauseAuto: '',
    rootCauseNote: '',
    correctiveAction: '',
    suggestedAction: '',
    ahtMinutes: 0,
    bookingRate: 0,
    attendRate: 0,
    raw: {
      identity: { employee_id: id, name, month: 'July', team, position },
      position,
      raw_data: {},
      calls: { inbound: 0, outbound: 0, total_handled: 0, abandoned: 0, aht_raw: '' },
      geo: {
        bookings: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
        attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
      },
      actual: { booking_rate: 0, attend_rate: 0, abandon_rate: 0 },
      achievement: { booking_ach: 0, attend_ach: 0 },
      evaluation: { score: 0.8, grade: 'B' },
    },
  };
}

describe('employee directory filters', () => {
  const rows = [
    row('E2', 'Zainab', 'Outbound', 'Agent'),
    row('E1', 'Aya', 'Outbound', 'Supervisor'),
    row('E3', 'Mona', 'Inbound', 'Agent'),
  ];

  it('filters by canonical team and position and sorts by employee name', () => {
    expect(getEmployeeDirectoryRows(rows, 'Outbound', 'Agent').map((item) => item.id)).toEqual(['E2']);
    expect(getEmployeeDirectoryRows(rows, 'Outbound', ALL_EMPLOYEE_POSITIONS).map((item) => item.name)).toEqual(['Aya', 'Zainab']);
  });

  it('exposes unique team and position options', () => {
    expect(getEmployeeDirectoryTeams(rows)).toEqual(['Inbound', 'Outbound']);
    expect(getEmployeeDirectoryPositions(rows, 'Outbound')).toEqual(['Agent', 'Supervisor']);
    expect(getEmployeeDirectoryPosition(row('E4', 'No Position', 'Outbound'))).toBe('Unassigned');
  });
});
