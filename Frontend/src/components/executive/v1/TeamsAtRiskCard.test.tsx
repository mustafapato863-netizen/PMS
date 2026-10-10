import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { getGradeClassOrNull } from '../../../constants/grades';
import type { ExecutiveTeam, ExecutiveTeamFlag } from '../../../features/executive/types';
import type { BasisComparisonContext } from '../../../features/evaluation/scoringBasisComparison';
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
    render(<MemoryRouter><TeamsAtRiskCard teams={[
      team('Grade C team', 89.9, ['grade_c']),
      team('Grade D team', 75, ['grade_d']),
      team('Grade E team', 60, ['grade_e']),
      team('Declining B team', 92, ['falling_2_months']),
      team('Stable B team', 90, []),
      team('Stable A team', 95, []),
      team('Unscored team', null, []),
    ]} /></MemoryRouter>);

    expect(screen.getByText('Grade C/D/E teams in the selected scope')).toBeInTheDocument();
    expect(screen.getAllByTestId('risk-row')).toHaveLength(3);
    expect(screen.getByText('Grade C team')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Grade C team' })).toHaveAttribute('href', '/team/grade-c-team');
    expect(screen.getByText('Grade C')).toBeInTheDocument();
    expect(screen.queryByText('Declining B team')).not.toBeInTheDocument();
    expect(screen.queryByText('Stable B team')).not.toBeInTheDocument();
    expect(screen.queryByText('Stable A team')).not.toBeInTheDocument();
    expect(screen.queryByText('Unscored team')).not.toBeInTheDocument();
  });

  it('shows every team, including Grade A and healthy teams, in the all-teams scope', () => {
    render(<MemoryRouter initialEntries={['/executive']}><TeamsAtRiskCard teams={[
      team('Grade C team', 89.9, ['grade_c']),
      team('Stable B team', 90, []),
      team('Stable A team', 95, []),
      team('Unscored team', null, []),
    ]} /></MemoryRouter>);

    expect(screen.getAllByTestId('risk-row')).toHaveLength(1);
    expect(screen.queryByText('Stable A team')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /all teams/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Show all teams' }));

    expect(screen.getByRole('heading', { name: 'All teams' })).toBeInTheDocument();
    expect(screen.getAllByTestId('risk-row')).toHaveLength(4);
    expect(screen.getByText('Stable A team')).toBeInTheDocument();
    expect(screen.getByText('Stable B team')).toBeInTheDocument();
    expect(screen.getByText('Unscored team')).toBeInTheDocument();
    expect(screen.getAllByText('No active risk flags')).toHaveLength(3);
    fireEvent.click(screen.getByRole('button', { name: 'Show at-risk teams' }));
    expect(screen.getAllByTestId('risk-row')).toHaveLength(1);
  });

  it('shows one evaluation-settings note for every team that shares it', () => {
    const basis: BasisComparisonContext = {
      state: 'changed',
      like_for_like: false,
      raw_performance: 'unchanged',
      membership: 'stable',
      reasons: ['target'],
      message: 'Scores can be affected by evaluation settings. Comparable raw performance is unchanged.',
    };
    render(<MemoryRouter><TeamsAtRiskCard teams={[
      { ...team('Grade C team', 80, ['grade_c']), basis_context: basis },
      { ...team('Grade D team', 70, ['grade_d']), basis_context: basis },
    ]} /></MemoryRouter>);

    expect(screen.getAllByTestId('basis-comparison-note')).toHaveLength(1);
    expect(screen.getByTestId('basis-comparison-note')).toHaveTextContent('Scores can be affected by evaluation settings.');
    expect(screen.getByTestId('basis-comparison-note')).toHaveTextContent('Comparable raw performance is unchanged.');
    expect(screen.getAllByTestId('risk-row')).toHaveLength(2);
  });

  it('keeps the selected branch and level when opening a team dashboard', () => {
    render(
      <MemoryRouter initialEntries={['/executive?branch=sharjah&level=Managerial&period=2026-06']}>
        <TeamsAtRiskCard teams={[team('Stable A team', 96, [])]} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Show all teams' }));

    expect(screen.getByRole('link', { name: 'Stable A team' })).toHaveAttribute(
      'href',
      '/team/stable-a-team?branch=sharjah&performance_level=Managerial',
    );
  });
});
