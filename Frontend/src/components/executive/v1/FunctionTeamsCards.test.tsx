import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import type { ExecutivePeriod, ExecutiveTeam } from '../../../features/executive/types';
import { TeamLeaderboardCard } from './FunctionTeamsCards';

const effective: ExecutivePeriod = { key: '2026-06', year: 2026, month: 'June' };

function team(name: string, score: number | null): ExecutiveTeam {
  return {
    team: name,
    function: 'RCM',
    regions: ['UAE'],
    employees: 12,
    score,
    previous_score: null,
    change: null,
    gap: score === null ? null : score - 100,
    grade: score === null ? null : score >= 90 ? 'B' : 'C',
    trend: [],
    vs_function_avg: null,
    rank_in_function: null,
    flags: [],
    flag_detail: null,
  };
}

describe('TeamLeaderboardCard', () => {
  it('ranks teams highest first without applying the employee threshold to teams', () => {
    render(
      <MemoryRouter>
        <TeamLeaderboardCard
          teams={[team('Coding', 89.9), team('Submission', 90), team('Re-Submission', null)]}
          fn="RCM"
          effective={effective}
          previous={null}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText('RCM teams ranked by June score — highest first')).toBeInTheDocument();

    const belowThresholdRow = screen.getByText('Coding').closest('[role="row"]');
    expect(belowThresholdRow).not.toBeNull();
    expect(within(belowThresholdRow as HTMLElement).queryByText('Below 90%')).not.toBeInTheDocument();

    const atThresholdRow = screen.getByText('Submission').closest('[role="row"]');
    expect(atThresholdRow).not.toBeNull();
    expect(within(atThresholdRow as HTMLElement).queryByText('Below 90%')).not.toBeInTheDocument();

    const unavailableRow = screen.getByText('Re-Submission').closest('[role="row"]');
    expect(unavailableRow).not.toBeNull();
    expect(within(unavailableRow as HTMLElement).queryByText('Below 90%')).not.toBeInTheDocument();
    expect(screen.getAllByTestId('leaderboard-row').map((row) => within(row).getByRole('link').textContent)).toEqual(['Submission', 'Coding', 'Re-Submission']);
  });

  it('opens Marketing role details in the shared summary while retaining filters', () => {
    render(<MemoryRouter initialEntries={['/function-summary/marketing?region=UAE&level=Managerial']}><TeamLeaderboardCard teams={[{ ...team('Social Media', 88), function: 'Marketing', position: 'Social Media' }]} fn="Marketing" effective={effective} previous={null} /></MemoryRouter>);
    expect(screen.getByRole('link', { name: 'Social Media' })).toHaveAttribute('href', '/function-summary/marketing?region=UAE&level=Managerial&position=Social+Media');
    expect(screen.getByRole('columnheader', { name: 'Role' })).toBeInTheDocument();
  });
});
