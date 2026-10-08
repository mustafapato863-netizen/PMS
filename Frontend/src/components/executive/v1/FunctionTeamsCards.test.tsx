import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import type { ExecutivePeriod, ExecutiveTeam } from '../../../features/executive/types';
import { TeamLeaderboardCard, TeamsNeedingAttentionCard } from './FunctionTeamsCards';

const mediaBuyer: ExecutiveTeam = {
  team: 'Media Buyer', position: 'Media Buyer', source_team: 'Marketing', function: 'Marketing',
  regions: ['EGY'], employees: 2, score: 56.5, previous_score: 50.8, change: 5.7,
  gap: -43.5, grade: 'E', trend: [], vs_function_avg: -20.6, rank_in_function: 9,
  flags: ['grade_e'], flag_detail: null,
};
const coding: ExecutiveTeam = { ...mediaBuyer, team: 'Coding', position: null, source_team: undefined, function: 'RCM' };
const effective: ExecutivePeriod = { key: '2026-06', year: 2026, month: 'June' };

function team(name: string, score: number | null): ExecutiveTeam {
  return {
    team: name, function: 'RCM', regions: ['UAE'], employees: 12, score,
    previous_score: null, change: null, gap: score === null ? null : score - 100,
    grade: score === null ? null : score >= 90 ? 'B' : 'C', trend: [],
    vs_function_avg: null, rank_in_function: null, flags: [], flag_detail: null,
  };
}

describe('TeamLeaderboardCard', () => {
  it('ranks teams highest first without applying the employee threshold to teams', () => {
    render(<MemoryRouter><TeamLeaderboardCard
      teams={[team('Coding', 89.9), team('Submission', 90), team('Re-Submission', null)]}
      fn="RCM" effective={effective} previous={null}
    /></MemoryRouter>);
    expect(screen.getByText('RCM teams ranked by June score — highest first')).toBeInTheDocument();
    for (const name of ['Coding', 'Submission', 'Re-Submission']) {
      const row = screen.getByText(name).closest('[role="row"]');
      expect(row).not.toBeNull();
      expect(within(row as HTMLElement).queryByText('Below 90%')).not.toBeInTheDocument();
    }
    expect(screen.getAllByTestId('leaderboard-row').map((row) => within(row).getByRole('link').textContent))
      .toEqual(['Submission', 'Coding', 'Re-Submission']);
  });

  it('opens Marketing role details on their own sheet while retaining scope', () => {
    render(<MemoryRouter initialEntries={['/function-summary/marketing?region=UAE&level=Managerial']}>
      <TeamLeaderboardCard teams={[{ ...team('Social Media', 88), function: 'Marketing', position: 'Social Media' }]}
        fn="Marketing" effective={effective} previous={null} />
    </MemoryRouter>);
    expect(screen.getByRole('link', { name: 'Social Media' })).toHaveAttribute('href', '/team/marketing?region=UAE&performance_level=Managerial&position=Social+Media');
    expect(screen.getByRole('columnheader', { name: 'Role' })).toBeInTheDocument();
  });
});

function Location() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}{location.search}</output>;
}

const surfaces = [
  { name: 'leaderboard', component: (team: ExecutiveTeam) => <TeamLeaderboardCard teams={[team]} fn={team.function!} effective={null} previous={null} /> },
  { name: 'attention', component: (team: ExecutiveTeam) => <TeamsNeedingAttentionCard teams={[team]} fn={team.function!} /> },
];

describe.each(surfaces)('Function detail links: $name', ({ component }) => {
  it('opens the Media Buyer sheet instead of filtering the function summary', () => {
    render(<MemoryRouter initialEntries={['/function-summary/marketing?period=2026-08&region=EGY&branch=dubai&level=Employee&team=Marketing&position=Content+Writer']}>
      {component(mediaBuyer)}<Location />
    </MemoryRouter>);
    const link = screen.getByRole('link', { name: 'Media Buyer' });
    const target = new URL(link.getAttribute('href')!, 'http://local');
    expect(target.pathname).toBe('/team/marketing');
    expect(target.searchParams.get('position_view')).toBe('Media Buyer');
    expect(target.searchParams.get('position')).toBeNull();
    expect(target.searchParams.get('month')).toBe('August');
    expect(target.searchParams.get('year')).toBe('2026');
    expect(target.searchParams.get('performance_level')).toBe('Employee');
    expect(target.searchParams.get('branch')).toBe('dubai');
    expect(target.searchParams.get('region')).toBe('EGY');
    fireEvent.click(link);
    expect(screen.getByTestId('location')).toHaveTextContent('/team/marketing?');
  });

  it('opens the selected team dashboard with the current period and scope', () => {
    render(<MemoryRouter initialEntries={['/function-summary/rcm?period=2026-06&branch=sharjah&region=UAE&level=Corporate&team=Pre-Approvals&sub_team=Other&position=Other']}>
      {component(coding)}
    </MemoryRouter>);
    const target = new URL(screen.getByRole('link', { name: 'Coding' }).getAttribute('href')!, 'http://local');
    expect(target.pathname).toBe('/team/coding');
    expect(target.searchParams.get('month')).toBe('June');
    expect(target.searchParams.get('year')).toBe('2026');
    expect(target.searchParams.get('branch')).toBe('sharjah');
    expect(target.searchParams.get('region')).toBe('UAE');
    expect(target.searchParams.get('performance_level')).toBe('Corporate');
    expect(target.searchParams.has('team')).toBe(false);
    expect(target.searchParams.has('sub_team')).toBe(false);
    expect(target.searchParams.has('position')).toBe(false);
  });

  it('encodes role names without treating them as synthetic teams', () => {
    const team = { ...mediaBuyer, team: 'Media Buyer & SEO Manager', position: 'Media Buyer & SEO Manager' };
    render(<MemoryRouter>{component(team)}</MemoryRouter>);
    const target = new URL(screen.getByRole('link', { name: team.team }).getAttribute('href')!, 'http://local');
    expect(target.pathname).toBe('/team/marketing');
    expect(target.searchParams.get('position_view')).toBe(team.position);
  });

  it('keeps a managerial Marketing role on its balanced scorecard route', () => {
    render(<MemoryRouter initialEntries={['/function-summary/marketing?period=2026-08&level=Managerial']}>
      {component(mediaBuyer)}
    </MemoryRouter>);
    const target = new URL(screen.getByRole('link', { name: 'Media Buyer' }).getAttribute('href')!, 'http://local');
    expect(target.pathname).toBe('/team/marketing');
    expect(target.searchParams.get('performance_level')).toBe('Managerial');
    expect(target.searchParams.get('position')).toBe('Media Buyer');
    expect(target.searchParams.has('position_view')).toBe(false);
  });

  it('ignores All levels and invalid period keys without losing legacy dates', () => {
    render(<MemoryRouter initialEntries={['/function-summary/marketing?period=2026-99&year=2025&month=June&level=All']}>
      {component(mediaBuyer)}
    </MemoryRouter>);
    const target = new URL(screen.getByRole('link', { name: 'Media Buyer' }).getAttribute('href')!, 'http://local');
    expect(target.searchParams.get('year')).toBe('2025');
    expect(target.searchParams.get('month')).toBe('June');
    expect(target.searchParams.has('performance_level')).toBe(false);
    expect(target.searchParams.get('position_view')).toBe('Media Buyer');
  });
});
