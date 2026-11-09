import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import TeamDashboardView from './TeamDashboardView';
import { TEAM_DB_NAME_MAP, TEAM_ID_MAP, TEAM_NAME_MAP, teamPath } from '../types';

const roleState = vi.hoisted(() => ({ role: 'Admin', allowsTeam: true }));
const performanceState = vi.hoisted(() => ({
  agents: [] as Array<{ identity: { employee_id?: string; team: string; month: string }; year: number }>,
  calls: vi.fn(),
  teamDataCalls: vi.fn(),
  teamConfigCalls: vi.fn(),
}));

vi.mock('../context/RoleContext', () => ({
  useUserRole: () => ({ role: roleState.role, fetchWithRole: vi.fn() }),
}));
vi.mock('../context/auth', () => ({ useAuth: () => ({ currentUser: null }) }));
vi.mock('../features/executive/useFunctionScope', () => ({
  useFunctionScope: () => ({ restricted: !roleState.allowsTeam, ready: true, allowed: [], allowsTeam: () => roleState.allowsTeam }),
}));
vi.mock('../hooks/useTeamConfig', () => ({
  useTeamConfig: (teamName: string) => {
    performanceState.teamConfigCalls(teamName);
    return { data: undefined };
  },
}));
vi.mock('../hooks/api/useInsightsWorkspace', () => ({ useInsightsWorkspace: () => ({ data: undefined }) }));
vi.mock('../hooks/useActionStore', () => ({
  useActionStore: () => ({ getActionsForEmployee: () => [], getAllActions: () => [] }),
}));
vi.mock('../lib/apiClient', () => ({ apiFetch: vi.fn(() => Promise.resolve({ success: false })) }));
vi.mock('../components/team/BalancedScorecardWorkspace', () => ({
  default: ({ displayName }: { displayName: string }) => <h2>{displayName}</h2>,
}));
vi.mock('../hooks/usePerformanceData', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../hooks/usePerformanceData')>()),
  // No agents for any team: the page renders its header and the empty state, which is all these tests read.
  useTeamData: (...args: unknown[]) => (performanceState.teamDataCalls(...args), {
    rows: [], avgScore: null, classCounts: { A: 0, B: 0, C: 0, D: 0, E: 0 }, pctAB: 0, pctDE: 0,
    totalAgents: 0, uniqueTeamCount: 0, prevMonth: null, loading: false, dataSource: null,
    errorMessage: null, prevAvgScore: null, prevPctAB: null, prevPctDE: null, prevTotalAgents: null,
  }),
  usePerformanceData: (...args: unknown[]) => {
    performanceState.calls(...args);
    return { uniqueMonths: [], agents: performanceState.agents };
  },
}));

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="team-location-probe">{location.pathname}{location.search}</div>;
}

function renderTeamPage(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/team/:teamId" element={<><TeamDashboardView /><LocationProbe /></>} />
        <Route path="/executive" element={<p>Executive Summary page</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

/** Title the team page shows for each known name: the canonical team's display name (merged view for OP/IP Final sources). */
const EXPECTED_TITLE: Record<string, string> = {
  'Administration': 'Administration',
  'Call Center': 'Call Center',
  'CSR': 'CSR',
  'Finance': 'Finance',
  'Human Resources': 'Human Resources',
  'IT': 'IT',
  'Offshore Admin & Management': 'Administration',
  'Coding': 'Coding',
  'Coding EGY': 'Coding',
  'Inbound': 'Inbound',
  'Marketing': 'Marketing',
  'Outbound': 'Outbound',
  'Pharmacy': 'Pharmacy',
  'Pre-Approvals': 'Pre-Approvals',
  'Pre-Approvals IP Elective': 'Pre-Approvals IP Elective',
  'Pre-Approvals IP Elective Dubai': 'Pre-Approvals IP Elective',
  'Pre-Approvals IP Final': 'Pre-Approvals IP Final',
  'Pre-Approvals IP Final Dubai': 'Pre-Approvals IP Final',
  'Pre-Approvals IP Final SHJAJM': 'Pre-Approvals IP Final',
  'Pre-Approvals IP': 'Pre-Approvals IP',
  'Pre-Approvals IP Offshore': 'Pre-Approvals IP Offshore',
  'Pre-Approvals OP Dubai': 'Pre-Approvals OP Final',
  'Pre-Approvals OP Final': 'Pre-Approvals OP Final',
  'Pre-Approvals OP Final SHJAJM': 'Pre-Approvals OP Final',
  'RCM': 'RCM',
  'Re-Submission': 'Re-Submission',
  'Re-Submission EGY': 'Re-Submission',
  'Resubmission': 'Re-Submission',
  'Sales': 'Sales',
  'Submission': 'Submission',
  'Submission EGY': 'Submission',
};

const KNOWN_NAMES = [...new Set([
  ...Object.keys(TEAM_ID_MAP),
  ...Object.values(TEAM_NAME_MAP),
  ...Object.values(TEAM_DB_NAME_MAP),
])].sort();

beforeEach(() => {
  roleState.role = 'Admin';
  roleState.allowsTeam = true;
  performanceState.agents = [];
  performanceState.calls.mockClear();
  performanceState.teamDataCalls.mockClear();
  performanceState.teamConfigCalls.mockClear();
});

describe('team page resolution', () => {
  it('keeps the selected year when loading a historical team period', () => {
    renderTeamPage('/team/re-submission?region=EGY&period=2025-09');
    expect(performanceState.teamDataCalls).toHaveBeenCalled();
    expect(performanceState.teamDataCalls.mock.calls.at(-1)?.[1]).toBe('2025-09');
  });
  it.each([
    ['coding', 'Coding EGY'],
    ['submission', 'Submission EGY'],
  ])('uses the Egypt source for %s history and available periods', (route, source) => {
    performanceState.agents = [
      { identity: { team: source, month: 'June' }, year: 2026 },
      { identity: { team: 'Unrelated', month: 'March' }, year: 2026 },
    ];
    renderTeamPage(`/team/${route}?region=EGY`);
    expect(performanceState.calls).toHaveBeenCalledWith('All', 'all', 'EGY', 'All', true, source);
    expect(screen.getByText(/June 2026/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /filters/i }));
    expect(document.querySelector('option[value="June"]')).toBeInTheDocument();
    expect(document.querySelector('option[value="March"]')).not.toBeInTheDocument();
  });

  it('includes both Egyptian re-submission source aliases in available periods', () => {
    performanceState.agents = [
      { identity: { team: 'Resubmission', month: 'June' }, year: 2026 },
      { identity: { team: 'Re-Submission EGY', month: 'July' }, year: 2026 },
    ];
    renderTeamPage('/team/re-submission?region=EGY');
    expect(performanceState.calls).toHaveBeenCalledWith('All', 'all', 'EGY', 'All', true, undefined);
    expect(performanceState.teamConfigCalls).toHaveBeenCalledWith('Resubmission');
    expect(screen.getByText(/June 2026/)).toBeInTheDocument();
    expect(screen.getByText(/July 2026/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /filters/i }));
    expect(document.querySelector('option[value="June"]')).toBeInTheDocument();
    expect(document.querySelector('option[value="July"]')).toBeInTheDocument();
  });

  it('switches between Egypt and UAE on the shared /team/re-submission route and preserves legacy URLs with period/month', () => {
    performanceState.agents = [
      { identity: { employee_id: 'E1', team: 'Resubmission', month: 'June' }, year: 2026 },
      { identity: { employee_id: 'E1', team: 'Re-Submission EGY', month: 'June' }, year: 2026 },
      { identity: { employee_id: 'U1', team: 'Re-Submission', month: 'August' }, year: 2026 },
    ];
    const uaeView = renderTeamPage('/team/re-submission?region=UAE');
    expect(performanceState.calls).toHaveBeenCalledWith('All', 'all', 'UAE', 'All', true, 'Re-Submission');
    expect(performanceState.teamConfigCalls).toHaveBeenCalledWith('Re-Submission');
    expect(screen.getByRole('heading', { level: 2, name: 'Re-Submission' })).toBeInTheDocument();
    expect(screen.getByText(/August 2026/)).toBeInTheDocument();
    expect(screen.queryByText(/June 2026/)).not.toBeInTheDocument();
    uaeView.unmount();

    const legacy1 = renderTeamPage('/team/resubmission?month=June');
    expect(screen.getByTestId('team-location-probe').textContent).toBe('/team/re-submission?month=June&region=EGY');
    expect(screen.getByRole('heading', { level: 2, name: 'Re-Submission' })).toBeInTheDocument();
    legacy1.unmount();

    const legacy2 = renderTeamPage('/team/re-submission-egy?period=2026-06');
    expect(screen.getByTestId('team-location-probe').textContent).toBe('/team/re-submission?period=2026-06&region=EGY');
    expect(screen.getByRole('heading', { level: 2, name: 'Re-Submission' })).toBeInTheDocument();
    legacy2.unmount();
  });

  it('blocks unauthorized team access with Authorization Context Restricted', () => {
    roleState.allowsTeam = false;
    renderTeamPage('/team/re-submission?region=EGY');
    expect(screen.getByText('Authorization Context Restricted')).toBeInTheDocument();
  });
  it('has a title expectation for every known team name and display name', () => {
    expect(KNOWN_NAMES.filter((name) => !(name in EXPECTED_TITLE))).toEqual([]);
  });

  it.each(KNOWN_NAMES)('opens the same team for teamPath(%s), titled with its display name', (name) => {
    const path = teamPath(name);
    renderTeamPage(path);
    expect(screen.getByRole('heading', { level: 2, name: EXPECTED_TITLE[name] })).toBeInTheDocument();
    expect(screen.queryByText('Team not found')).not.toBeInTheDocument();
  });

  it('keeps corporate finance on the team dashboard', async () => {
    renderTeamPage('/team/finance?performance_level=Corporate');
    expect(screen.queryByRole('heading', { name: 'Position overview finance' })).not.toBeInTheDocument();
    expect(await screen.findByRole('heading', { level: 2, name: 'Finance' })).toBeInTheDocument();
  });

  it.each(['/team/pre-approvals', '/team/pre-approvals-ip-offshore', '/team/PRE-APPROVALS-IP-OFFSHORE'])(
    'still opens Pre-Approvals IP Offshore from the legacy link %s',
    (path) => {
      renderTeamPage(path);
      expect(screen.getByRole('heading', { level: 2, name: 'Pre-Approvals IP Offshore' })).toBeInTheDocument();
    },
  );

  it('shows the not-found state with the id for an unknown team, and never an invented title', () => {
    renderTeamPage('/team/pre-approvals-ip-offshor');
    expect(screen.getAllByText('Team not found').length).toBeGreaterThan(0);
    expect(screen.getByText(/No team matches “pre-approvals-ip-offshor”/)).toBeInTheDocument();
    expect(screen.queryByText(/PRE Approvals/)).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 2, name: /Pre-Approvals/ })).not.toBeInTheDocument();
  });
});

function breadcrumbs() {
  const nav = screen.getByRole('navigation', { name: 'Breadcrumb' });
  const labels = Array.from(nav.querySelectorAll('li')).map((item) => item.textContent);
  const links = within(nav).queryAllByRole('link').map((link) => link.getAttribute('href'));
  return { labels, links };
}

describe('team page breadcrumbs', () => {
  it('follows Executive Summary > Function > Parent view > Sub-team for a UAE workflow the parent page shows', () => {
    renderTeamPage('/team/pre-approvals-op-final');
    expect(breadcrumbs()).toEqual({
      labels: ['Executive Summary', 'RCM', 'Pre-Approvals', 'Pre-Approvals OP Final'],
      links: ['/executive', '/function-summary/rcm', '/team/pre-approvals-uae'],
    });
  });

  it('shows Function > Sub-team for Pre-Approvals IP Offshore, with no Pre-Approvals crumb it cannot open', () => {
    renderTeamPage('/team/pre-approvals');
    expect(breadcrumbs()).toEqual({
      labels: ['Executive Summary', 'RCM', 'Pre-Approvals IP Offshore'],
      links: ['/executive', '/function-summary/rcm'],
    });
  });

  it('shows the parent view it sits under for a team in the Call Center view, without repeating the function', () => {
    renderTeamPage('/team/inbound');
    expect(breadcrumbs()).toEqual({
      labels: ['Executive Summary', 'Call Center', 'Inbound'],
      links: ['/executive', '/function-summary/call-center'],
    });
  });

  it('shows Function > Team for a stand-alone team', () => {
    renderTeamPage('/team/coding');
    expect(breadcrumbs()).toEqual({
      labels: ['Executive Summary', 'RCM', 'Coding'],
      links: ['/executive', '/function-summary/rcm'],
    });
  });

  it('opens the Executive Summary filtered to the function for a role without the Function Summary', () => {
    roleState.role = 'Manager';
    renderTeamPage('/team/pre-approvals-op-final');
    expect(breadcrumbs().links).toEqual(['/executive', '/executive?function=RCM', '/team/pre-approvals-uae']);
  });
});
