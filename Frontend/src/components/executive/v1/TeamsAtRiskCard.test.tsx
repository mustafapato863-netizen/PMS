import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
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
    render(<TeamsAtRiskCard limit={10} teams={[
      team('Grade C team', 89.9, ['grade_c']),
      team('Grade D team', 75, ['grade_d']),
      team('Grade E team', 60, ['grade_e']),
      team('Declining B team', 92, ['falling_2_months']),
      team('Stable B team', 90, []),
      team('Stable A team', 95, []),
      team('Unscored team', null, []),
    ]} />);

    expect(screen.getByText('Grade C/D/E, or score falling 2 consecutive months')).toBeInTheDocument();
    expect(screen.getAllByTestId('risk-row')).toHaveLength(4);
    expect(screen.getByText('Grade C team')).toBeInTheDocument();
    expect(screen.getByText('Grade C')).toBeInTheDocument();
    expect(screen.getByText('Declining B team')).toBeInTheDocument();
    expect(screen.getByText('Falling 2 mo')).toBeInTheDocument();
    expect(screen.queryByText('Stable B team')).not.toBeInTheDocument();
    expect(screen.queryByText('Stable A team')).not.toBeInTheDocument();
    expect(screen.queryByText('Unscored team')).not.toBeInTheDocument();
  });
});
