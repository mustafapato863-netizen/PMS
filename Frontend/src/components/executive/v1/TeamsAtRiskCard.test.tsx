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
  it('opens a Pre-Approvals team on its canonical page and keeps the branch and level filters', () => {
    render(<MemoryRouter initialEntries={['/executive?branch=sharjah&level=Managerial']}><TeamsAtRiskCard teams={[
      team('Pre-Approvals IP Offshore', 70, ['grade_d']),
    ]} /></MemoryRouter>);

    expect(screen.getByRole('link', { name: 'Pre-Approvals IP Offshore' }))
      .toHaveAttribute('href', '/team/pre-approvals?branch=sharjah&performance_level=Managerial&region=UAE');
  });

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

    expect(screen.getByText('Score under 90%, ranked from worst score')).toBeInTheDocument();
    expect(screen.getAllByTestId('risk-row')).toHaveLength(3);
    expect(screen.getAllByRole('link').map((link) => link.textContent)).toEqual(['Grade E team', 'Grade D team', 'Grade C team']);
    expect(screen.getByText('Grade E team is the lowest-scoring team at 60.0%.')).toBeInTheDocument();
    expect(screen.getByText('Grade C team')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Grade C team' })).toHaveAttribute('href', '/team/grade-c-team?region=UAE');
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

  it('omits evaluation-settings boilerplate while keeping at-risk rows visible', () => {
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

    expect(screen.queryByTestId('basis-comparison-note')).not.toBeInTheDocument();
    expect(screen.getAllByTestId('risk-row')).toHaveLength(2);
  });

  it('ranks worst score first, breaks score ties by gap share, and puts unscored teams last', () => {
    render(<MemoryRouter><TeamsAtRiskCard teams={[
      { ...team('Better score, big gap', 85, ['grade_c']), gap_share_percent: 40, employees: 10 },
      { ...team('Worst score, small gap', 70, ['grade_d']), gap_share_percent: 5, employees: 10 },
      { ...team('Worst score, big gap', 70, ['grade_d']), gap_share_percent: 30, employees: 10 },
      { ...team('Unscored team', null, []), gap_share_percent: 50, employees: 10 },
    ]} /></MemoryRouter>);

    expect(screen.getByText('Worst score, big gap is the lowest-scoring team at 70.0%.')).toBeInTheDocument();
    expect(screen.getAllByRole('link').map((link) => link.textContent)).toEqual([
      'Worst score, big gap', 'Worst score, small gap', 'Better score, big gap',
    ]);
    fireEvent.click(screen.getByRole('button', { name: 'Show all teams' }));
    expect(screen.getByText('Every team in the selected scope, ranked from worst score')).toBeInTheDocument();
    expect(screen.getAllByRole('link').map((link) => link.textContent)).toEqual([
      'Worst score, big gap', 'Worst score, small gap', 'Better score, big gap', 'Unscored team',
    ]);
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
      '/team/stable-a-team?branch=sharjah&performance_level=Managerial&region=UAE&year=2026&month=June',
    );
  });

  it('renders the 6 Figma columns with bottleneck KPI, status labels, and Review Team action', () => {
    render(
      <MemoryRouter>
        <TeamsAtRiskCard
          teams={[
            {
              ...team('CSR UAE', 68.4, ['grade_e']),
              function: 'CSR',
              employees: 28,
              gap_share_percent: 21.4,
              flag_detail: {
                kpi_key: 'fcr',
                kpi_label: 'First Call Resolution',
                kpi_direction: 'higher_better',
                current_value: 71.0,
                target_value: 85.0,
                unit: '%',
                text: 'First Call Resolution',
              },
            },
            {
              ...team('Pre-Approvals IP Final', 74.2, ['grade_d', 'falling_2_months']),
              employees: 22,
              gap_share_percent: 16.8,
            },
            {
              ...team('ER Dr · Sharjah', 84.6, ['grade_c']),
              function: 'ER Dr',
              employees: 14,
              gap_share_percent: 8.9,
            },
          ]}
        />
      </MemoryRouter>,
    );

    expect(screen.getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual([
      'Team & Scope',
      'Score & Grade',
      'Gap Share',
      'Primary Bottleneck KPI',
      'Status',
      'Action',
    ]);
    expect(screen.getByText('21.4% of gap')).toBeInTheDocument();
    expect(screen.getByText('First Call Resolution (71% vs 85%)')).toBeInTheDocument();
    expect(screen.getByText('Critical <70%')).toBeInTheDocument();
    expect(screen.getByText('Falling 2 mo')).toBeInTheDocument();
    expect(screen.getByText('Below 90%')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Review Team/i })).toHaveLength(3);
  });
});
