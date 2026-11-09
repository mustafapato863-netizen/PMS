import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import RcmEgyptTeamSummary from './RcmEgyptTeamSummary';
import RcmDomainSummary from './RcmDomainSummary';
import type { TeamAgentRow } from '../../hooks/usePerformanceData';
import type { AgentRecord, PerformanceLevel } from '../../types';

const ZERO_GEO = { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 };

const createRow = (id: string, name: string, team: string, score: number, plevel: PerformanceLevel = 'Employee'): TeamAgentRow => ({
  id,
  name,
  team,
  month: 'September',
  performanceLevel: plevel,
  score,
  gradeClass: 'C',
  gradeLabel: 'Needs Improvement',
  status: 'Below',
  rootCauseAuto: '',
  rootCauseNote: '',
  correctiveAction: '',
  suggestedAction: '',
  ahtMinutes: 0,
  bookingRate: 0,
  attendRate: 0,
  raw: {
    identity: { employee_id: id, name, month: 'September', team },
    performance_level: plevel,
    region: 'EGY',
  } as TeamAgentRow['raw'],
});

const createHossamAgent = (): AgentRecord => ({
  identity: {
    employee_id: 'SGHD70094',
    name: 'Hossam Mohamed Abdelsameea Tolba Ahmed',
    team: 'Pre-Approvals IP',
    month: 'September',
    position: 'Pre-Authorization Supervisor',
  },
  performance_level: 'Managerial',
  region: 'EGY',
  year: 2026,
  kpi_values: [],
  calls: { inbound: 0, outbound: 0, total_handled: 0, abandoned: 0, aht_raw: '00:00:00' },
  geo: { bookings: { ...ZERO_GEO }, attended: { ...ZERO_GEO } },
  actual: { booking_rate: 0, attend_rate: 0, abandon_rate: 0 },
  achievement: { booking_ach: 0, attend_ach: 0 },
  evaluation: { score: 88.61, grade: 'C' },
});

describe('RCM Summaries Team Score Display', () => {
  it('RcmEgyptTeamSummary displays Team score label and Hossam score for Pre-Approvals IP', () => {
    const specialistRow = createRow('SGHD70143', 'Nouran', 'Pre-Approvals IP', 76.78);
    const hossamAgent = createHossamAgent();

    render(
      <RcmEgyptTeamSummary
        rows={[specialistRow]}
        onTeamSelect={vi.fn()}
        allAgents={[hossamAgent]}
      />
    );

    // Score must be Hossam's score (88.6%), not specialist 76.8%
    expect(screen.getByText('88.6%')).toBeInTheDocument();
    // Label must be "Team score", not "Average employee score"
    expect(screen.getByText('Team score')).toBeInTheDocument();
    expect(screen.queryByText('Average employee score')).not.toBeInTheDocument();
  });

  it('RcmDomainSummary displays Team score label and Hossam score for pre_approvals domain', () => {
    const specialistRow = createRow('SGHD70143', 'Nouran', 'Pre-Approvals IP', 76.78);
    const hossamAgent = createHossamAgent();

    render(
      <RcmDomainSummary
        rows={[specialistRow]}
        onDomainSelect={vi.fn()}
        allAgents={[hossamAgent]}
      />
    );

    expect(screen.getByText('88.6%')).toBeInTheDocument();
    expect(screen.getByText('Team score')).toBeInTheDocument();
    expect(screen.queryByText('Average employee score')).not.toBeInTheDocument();
  });
});
