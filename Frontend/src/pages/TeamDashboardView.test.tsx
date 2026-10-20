import { render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import TeamDashboardView from './TeamDashboardView';
import { TEAM_DB_NAME_MAP, TEAM_ID_MAP, TEAM_NAME_MAP, teamPath } from '../types';

const roleState = vi.hoisted(() => ({ role: 'Admin' }));

vi.mock('../context/RoleContext', () => ({
  useUserRole: () => ({ role: roleState.role, fetchWithRole: vi.fn() }),
}));
vi.mock('../context/auth', () => ({ useAuth: () => ({ currentUser: null }) }));
vi.mock('../features/executive/useFunctionScope', () => ({
  useFunctionScope: () => ({ restricted: false, allowed: [], allowsTeam: () => true }),
}));
vi.mock('../hooks/useTeamConfig', () => ({ useTeamConfig: () => ({ data: undefined }) }));
vi.mock('../hooks/api/useInsightsWorkspace', () => ({ useInsightsWorkspace: () => ({ data: undefined }) }));
vi.mock('../hooks/useActionStore', () => ({
  useActionStore: () => ({ getActionsForEmployee: () => [], getAllActions: () => [] }),
}));
vi.mock('../lib/apiClient', () => ({ apiFetch: vi.fn(() => Promise.resolve({ success: false })) }));
vi.mock('./MarketingDashboardView', () => ({
  default: ({ teamId }: { teamId?: string }) => <h2>Position overview {teamId}</h2>,
}));
vi.mock('../components/team/BalancedScorecardWorkspace', () => ({
  default: ({ displayName }: { displayName: string }) => <h2>{displayName}</h2>,
}));
vi.mock('../hooks/usePerformanceData', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../hooks/usePerformanceData')>()),
  // No agents for any team: the page renders its header and the empty state, which is all these tests read.
  useTeamData: () => ({
    rows: [], avgScore: null, classCounts: { A: 0, B: 0, C: 0, D: 0, E: 0 }, pctAB: 0, pctDE: 0,
    totalAgents: 0, uniqueTeamCount: 0, prevMonth: null, loading: false, dataSource: null,
    errorMessage: null, prevAvgScore: null, prevPctAB: null, prevPctDE: null, prevTotalAgents: null,
  }),
  usePerformanceData: () => ({ uniqueMonths: [], agents: [] }),
}));

function renderTeamPage(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/team/:teamId" element={<TeamDashboardView />} />
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
  'Pre-Approvals IP Offshore': 'Pre-Approvals IP Offshore',
  'Pre-Approvals OP Dubai': 'Pre-Approvals OP Final',
  'Pre-Approvals OP Final': 'Pre-Approvals OP Final',
  'Pre-Approvals OP Final SHJAJM': 'Pre-Approvals OP Final',
  'RCM': 'RCM',
  'Re-Submission': 'Re-Submission',
  'Sales': 'Sales',
  'Submission': 'Submission',
};

const KNOWN_NAMES = [...new Set([
  ...Object.keys(TEAM_ID_MAP),
  ...Object.values(TEAM_NAME_MAP),
  ...Object.values(TEAM_DB_NAME_MAP),
])].sort();

beforeEach(() => {
  roleState.role = 'Admin';
});

describe('team page resolution', () => {
  it('has a title expectation for every known team name and display name', () => {
    expect(KNOWN_NAMES.filter((name) => !(name in EXPECTED_TITLE))).toEqual([]);
  });

  it.each(KNOWN_NAMES)('opens the same team for teamPath(%s), titled with its display name', (name) => {
    const path = teamPath(name);
    renderTeamPage(path);
    const teamId = path.split('/').pop() ?? '';
    const positionOverview = ['finance', 'human-resources', 'it', 'administration'].includes(teamId);
    expect(screen.getByRole('heading', {
      level: 2,
      name: positionOverview ? `Position overview ${teamId}` : EXPECTED_TITLE[name],
    })).toBeInTheDocument();
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
