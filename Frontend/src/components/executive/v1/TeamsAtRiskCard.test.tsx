import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { getGradeClassOrNull } from '../../../constants/grades';
import type { ExecutiveTeam, ExecutiveTeamFlag } from '../../../features/executive/types';
import TeamsAtRiskCard from './TeamsAtRiskCard';

function team(name: string, score: number | null, flags: ExecutiveTeamFlag[]): ExecutiveTeam {
  return {
    team: name,
    function: 'RCM',
    regions: ['UAE'],
    employees: 1,
    score,
    previous_score: null,
    change: null,
    gap: score === null ? null : score - 100,
    grade: getGradeClassOrNull(score),
    trend: [],
    vs_function_avg: null,
    rank_in_function: null,
    flags,
    flag_detail: null,
  };
}

describe('TeamsAtRiskCard', () => {
  it('includes Grade C/D/E and declining healthy teams, with matching flag labels', () => {
    render(<MemoryRouter><TeamsAtRiskCard limit={10} teams={[
      team('Grade C team', 89.9, ['grade_c']),
      team('Grade D team', 75, ['grade_d']),
      team('Grade E team', 60, ['grade_e']),
      team('Declining B team', 92, ['falling_2_months']),
      team('Stable B team', 90, []),
      team('Stable A team', 95, []),
      team('Unscored team', null, []),
    ]} /></MemoryRouter>);

    expect(screen.getByText('Grade C/D/E, or score falling 2 consecutive months')).toBeInTheDocument();
    expect(screen.getAllByTestId('risk-row')).toHaveLength(4);
    expect(screen.getByText('Grade C team')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Grade C team' })).toHaveAttribute('href', '/team/grade-c-team');
    expect(screen.getByText('Grade C')).toBeInTheDocument();
    expect(screen.getByText('Declining B team')).toBeInTheDocument();
    expect(screen.getByText('Falling 2 mo')).toBeInTheDocument();
    expect(screen.queryByText('Stable B team')).not.toBeInTheDocument();
    expect(screen.queryByText('Stable A team')).not.toBeInTheDocument();
    expect(screen.queryByText('Unscored team')).not.toBeInTheDocument();
  });

  it('shows every team, including Grade A and healthy teams, in the all-teams scope', () => {
    render(<MemoryRouter><TeamsAtRiskCard limit={2} showAllTeams teams={[
      team('Grade C team', 89.9, ['grade_c']),
      team('Stable B team', 90, []),
      team('Stable A team', 95, []),
      team('Unscored team', null, []),
    ]} /></MemoryRouter>);

    expect(screen.getByRole('heading', { name: 'All teams' })).toBeInTheDocument();
    expect(screen.getAllByTestId('risk-row')).toHaveLength(4);
    expect(screen.getByText('Stable A team')).toBeInTheDocument();
    expect(screen.getByText('Stable B team')).toBeInTheDocument();
    expect(screen.getByText('Unscored team')).toBeInTheDocument();
    expect(screen.getAllByText('No active risk flags')).toHaveLength(3);
  });

  it('keeps the selected branch and level when opening a team dashboard', () => {
    render(
      <MemoryRouter initialEntries={['/executive?branch=sharjah&level=Managerial&period=2026-06']}>
        <TeamsAtRiskCard showAllTeams teams={[team('Stable A team', 96, [])]} />
      </MemoryRouter>,
    );

    expect(screen.getByRole('link', { name: 'Stable A team' })).toHaveAttribute(
      'href',
      '/team/stable-a-team?branch=sharjah&performance_level=Managerial',
    );
  });
});
