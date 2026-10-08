import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { StrictMode, useState, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ThemeProvider } from '../../context/ThemeContext';
import { apiFetch } from '../../lib/apiClient';
import Sidebar from './Sidebar';
import { TEAM_ITEMS } from './sidebarTeamItems';

type MockUser = {
  id: string;
  name: string;
  username: string;
  role: 'Admin' | 'General Manager' | 'Manager' | 'Executive' | 'Viewer' | 'Agent' | 'Employee' | 'Performance Team' | 'Regional Manager' | 'Branch Director' | 'Function Director' | 'Function Viewer';
  employee_id?: string;
  has_unrestricted_team_access?: boolean;
  accessible_teams?: string[];
  accessible_functions?: string[];
  accessible_branches?: string[];
  accessible_regions?: string[];
};

const authState = vi.hoisted(() => ({
  user: {
    id: 'admin-1',
    name: 'Admin',
    username: 'admin',
    role: 'Admin',
    has_unrestricted_team_access: true,
    accessible_teams: [],
  } as MockUser,
}));

const DEFAULT_SCOPES = [{ team: 'Marketing', region: 'EGY', performance_level: 'Employee', position: 'Media Buyer' }];
const catalogState = vi.hoisted(() => ({
  scopes: [{ team: 'Marketing', region: 'EGY', performance_level: 'Employee', position: 'Media Buyer' }] as Array<{ team: string; region: string; performance_level: string; position: string }>,
}));

const ADMIN_USER: MockUser = {
  id: 'admin-1',
  name: 'Admin',
  username: 'admin',
  role: 'Admin',
  has_unrestricted_team_access: true,
  accessible_teams: [],
};

vi.mock('../../context/RoleContext', () => ({
  useUserRole: () => ({ role: authState.user.role }),
}));

vi.mock('../../context/auth', () => ({
  useAuth: () => ({
    currentUser: authState.user,
    logout: vi.fn(),
  }),
}));

vi.mock('../../hooks/api/usePerformanceCatalog', () => ({
  usePerformanceCatalog: () => ({
    data: {
      months: ['June'],
      periods: [{ year: 2026, month: 'June', key: '2026-06' }],
      scopes: catalogState.scopes,
    },
  }),
}));

vi.mock('../../lib/apiClient', () => ({
  apiFetch: vi.fn().mockResolvedValue({ success: true, data: [], scopes: [] }),
}));

const mockedApiFetch = vi.mocked(apiFetch);

const QueryWrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    {children}
  </QueryClientProvider>
);

const renderSidebar = (initialEntry = '/') => render(
  <MemoryRouter initialEntries={[initialEntry]}>
    <ThemeProvider>
      <Sidebar isOpen setIsOpen={vi.fn()} />
    </ThemeProvider>
  </MemoryRouter>, { wrapper: QueryWrapper },
);

const mockTeamConfigFetch = () => {
  mockedApiFetch.mockImplementation(async (path) => {
    if (path === '/api/config/teams') {
      return {
        success: true,
        data: [{ team: 'Marketing', performance_levels: { Employee: {} } }],
      } as never;
    }
    if (path === '/api/team-management/management-kpi-config/teams') {
      return {
        success: true,
        data: ['Marketing'],
        scopes: [{ id: 'marketing-management', name: 'Marketing', team_level: 'management' }],
      } as never;
    }
    return { success: true, data: [] } as never;
  });
};

describe('Sidebar team icons', () => {
  beforeEach(() => {
    mockedApiFetch.mockClear();
    authState.user = ADMIN_USER;
    catalogState.scopes = DEFAULT_SCOPES;
    mockTeamConfigFetch();
  });

  it('shares configuration requests across StrictMode remounts', async () => {
    render(<StrictMode><MemoryRouter><ThemeProvider><Sidebar isOpen setIsOpen={vi.fn()} /></ThemeProvider></MemoryRouter></StrictMode>, { wrapper: QueryWrapper });
    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledWith('/api/config/teams'));
    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledWith('/api/team-management/management-kpi-config/teams'));
    expect(mockedApiFetch.mock.calls.filter(([path]) => path === '/api/config/teams')).toHaveLength(1);
    expect(mockedApiFetch.mock.calls.filter(([path]) => path === '/api/team-management/management-kpi-config/teams')).toHaveLength(1);
  });

  it('uses a distinct icon for every known team', () => {
    const iconTypes = TEAM_ITEMS.map((item) => item.icon.type);

    expect(new Set(iconTypes).size).toBe(TEAM_ITEMS.length);
  });

  it('renders the full navigation shell without runtime icon errors', () => {
    renderSidebar();

    expect(screen.getByRole('complementary', { name: 'Primary navigation' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'SGH Hub' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Planning' })).toBeInTheDocument();
  });

  it('provides an accessible desktop collapse control', () => {
    const onToggleCollapsed = vi.fn();
    render(
      <MemoryRouter>
        <ThemeProvider>
          <Sidebar isOpen setIsOpen={vi.fn()} onToggleCollapsed={onToggleCollapsed} />
        </ThemeProvider>
      </MemoryRouter>, { wrapper: QueryWrapper },
    );

    const collapseButton = screen.getByRole('button', { name: 'Minimize navigation sidebar' });
    expect(collapseButton).toHaveAttribute('title', 'Minimize sidebar');
    fireEvent.click(collapseButton);
    expect(onToggleCollapsed).toHaveBeenCalledTimes(1);
  });

  it('keeps the collapsed header controls inside the compact rail', () => {
    render(
      <MemoryRouter>
        <ThemeProvider>
          <Sidebar isOpen setIsOpen={vi.fn()} isCollapsed onToggleCollapsed={vi.fn()} />
        </ThemeProvider>
      </MemoryRouter>, { wrapper: QueryWrapper },
    );

    const sidebar = screen.getByRole('complementary', { name: 'Primary navigation' });
    expect(sidebar).toHaveClass('is-collapsed');
    expect(screen.getByRole('button', { name: 'Expand navigation sidebar' })).toHaveClass('xl:min-w-8');
  });

  it.each(['Managerial', 'Corporate'])(
    'marks only Management Marketing active for the %s scope',
    async (performanceLevel) => {
      renderSidebar(`/team/marketing?performance_level=${performanceLevel}`);

      await waitFor(() => expect(screen.getAllByRole('link', { name: 'Marketing' })).toHaveLength(2));
      const marketingLinks = screen.getAllByRole('link', { name: 'Marketing' });
      const employeeLink = marketingLinks.find((link) => link.getAttribute('href')?.includes('performance_level=Employee'));
      const managementLink = marketingLinks.find((link) => link.getAttribute('href')?.includes('performance_level=Corporate'));

      expect(employeeLink).not.toHaveAttribute('aria-current');
      expect(managementLink).toHaveAttribute('aria-current', 'page');
    },
  );

  it('uses a canonical Employee URL and keeps Shared Functions Marketing exclusively active', async () => {
    renderSidebar('/team/marketing?performance_level=Employee');

    await waitFor(() => expect(screen.getByRole('link', { name: 'Marketing' })).toBeInTheDocument());
    const employeeLink = screen.getByRole('link', { name: 'Marketing' });

    expect(employeeLink).toHaveAttribute('href', '/team/marketing?performance_level=Employee');
    expect(employeeLink).toHaveAttribute('aria-current', 'page');
  });
});

describe('Sidebar General Manager navigation (stored role string)', () => {
  beforeEach(() => {
    mockTeamConfigFetch();
  });

  it('gives a General Manager product pages and personal account settings, not administration', () => {
    authState.user = {
      id: 'gm-1',
      name: 'Gina Grant',
      username: 'gm',
      role: 'General Manager',
      accessible_teams: [],
    };
    renderSidebar();

    for (const name of ['Reports', 'Insights', 'Planning', 'Corrective Actions', 'All Teams']) {
      expect(screen.getByRole('link', { name })).toBeInTheDocument();
    }
    expect(screen.getByRole('link', { name: 'Account settings' })).toHaveAttribute('href', '/account');
    expect(screen.queryByRole('link', { name: 'Administration' })).not.toBeInTheDocument();
    expect(screen.getByText('General Manager')).toBeInTheDocument();
  });

  it('does not treat a Manager with has_unrestricted_team_access as a General Manager', () => {
    authState.user = {
      id: 'mgr-all',
      name: 'Alma Teams',
      username: 'mgr-all',
      role: 'Manager',
      has_unrestricted_team_access: true,
      accessible_teams: [],
    };
    renderSidebar();

    // Executive v1 (Mustafa): Manager gets Reports, Corrective Actions and Planning — never Insights.
    expect(screen.queryByRole('link', { name: 'Insights' })).not.toBeInTheDocument();
    for (const name of ['Reports', 'Planning', 'Corrective Actions']) {
      expect(screen.getByRole('link', { name })).toBeInTheDocument();
    }
    expect(screen.getByRole('link', { name: 'Assigned Teams' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Account settings' })).toHaveAttribute('href', '/account');
    expect(screen.queryByText('General Manager')).not.toBeInTheDocument();
  });

  it('gives a scoped Manager the Executive v1 menu (no Insights) and personal account settings', () => {
    authState.user = {
      id: 'mgr-1',
      name: 'Mo Scoped',
      username: 'mgr',
      role: 'Manager',
      has_unrestricted_team_access: false,
      accessible_teams: ['Marketing'],
    };
    renderSidebar();

    expect(screen.queryByRole('link', { name: 'Insights' })).not.toBeInTheDocument();
    const general = ['Executive Summary', 'My Team · Marketing', 'Reports', 'Corrective Actions', 'Planning'];
    const links = screen.getAllByRole('link').map((link) => link.textContent?.trim());
    const positions = general.map((name) => links.indexOf(name));
    expect(positions.every((position) => position >= 0)).toBe(true);
    expect([...positions].sort((l, r) => l - r)).toEqual(positions);
    expect(screen.getByRole('link', { name: 'My Team · Marketing' })).toHaveAttribute('href', '/team/marketing');
    expect(screen.getByRole('link', { name: 'Account settings' })).toHaveAttribute('href', '/account');
    expect(screen.getByText('Manager')).toBeInTheDocument();
  });

  it('shows separate Administration and Account settings links to Admin', () => {
    authState.user = ADMIN_USER;
    renderSidebar();

    for (const name of ['Reports', 'Insights', 'Planning', 'Corrective Actions', 'Administration', 'Account settings', 'All Teams']) {
      expect(screen.getByRole('link', { name })).toBeInTheDocument();
    }
    expect(screen.queryByText('General Manager')).not.toBeInTheDocument();
  });

  it('shows Corrective Actions and personal account settings but not admin pages to Executive', () => {
    authState.user = { id: 'exec-1', name: 'Eve Exec', username: 'exec', role: 'Executive', accessible_teams: [] };
    renderSidebar();

    expect(screen.getByRole('link', { name: 'Corrective Actions' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Account settings' })).toHaveAttribute('href', '/account');
    for (const name of ['Reports', 'Insights', 'Planning']) {
      expect(screen.queryByRole('link', { name })).not.toBeInTheDocument();
    }
  });
});

describe('Function Viewer sidebar (Figma 48:3)', () => {
  beforeEach(() => {
    mockTeamConfigFetch();
    catalogState.scopes = ['Coding', 'Submission', 'Pre-Approvals IP Offshore', 'Pre-Approvals OP Final', 'Inbound', 'Marketing', 'CSR']
      .map((team) => ({ team, region: 'EGY', performance_level: 'Employee', position: 'Agent' }));
    authState.user = {
      id: 'fv-1', name: 'Laila Ashraf', username: 'laila', role: 'Function Viewer',
      accessible_teams: [], accessible_functions: ['RCM', 'Pre-Approvals'],
    };
  });

  it('shows Function Summary, only the assigned functions with their teams, and Reports', async () => {
    renderSidebar('/function-summary/rcm');
    expect(screen.getByText('FUNCTION VIEWER')).toBeInTheDocument();
    await screen.findByRole('link', { name: 'Function Summary' });
    expect(screen.getByRole('link', { name: 'Function Summary' })).toHaveAttribute('href', '/function-summary');
    expect(screen.getByRole('link', { name: 'RCM' })).toHaveAttribute('href', '/function-summary/rcm');
    expect(screen.getByRole('link', { name: 'Pre-Approvals' })).toHaveAttribute('href', '/function-summary/pre-approvals');
    expect(screen.getByRole('link', { name: 'Reports' })).toHaveAttribute('href', '/reports');
    expect(screen.queryByRole('link', { name: 'Call Center' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Marketing' })).not.toBeInTheDocument();

    // First function expanded: its teams (IP Offshore counts under RCM) link to read-only team dashboards.
    const rcmTeams = screen.getByRole('group', { name: 'RCM teams' });
    expect(within(rcmTeams).getByRole('link', { name: 'Coding' })).toHaveAttribute('href', '/team/coding');
    expect(within(rcmTeams).getByRole('link', { name: 'Pre-Approvals IP Offshore' })).toBeInTheDocument();
    expect(within(rcmTeams).queryByRole('link', { name: 'Inbound' })).not.toBeInTheDocument();
    expect(within(rcmTeams).getByRole('link', { name: 'Pre-Approvals OP Final' })).toBeInTheDocument();
  });

  it('keeps the legacy UAE-only grant usable without adding RCM or Offshore access', async () => {
    authState.user = { ...authState.user, accessible_functions: ['Pre-Approvals'] };
    renderSidebar('/function-summary/pre-approvals');
    const group = await screen.findByRole('group', { name: 'Pre-Approvals teams' });
    expect(within(group).getByRole('link', { name: 'Pre-Approvals OP Final' })).toBeInTheDocument();
    expect(within(group).queryByRole('link', { name: 'Pre-Approvals IP Offshore' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'RCM' })).not.toBeInTheDocument();
  });

  it('hides the employee tree, Shared Functions, product pages and Settings, and shows Read-only', () => {
    renderSidebar('/function-summary/rcm');
    for (const name of ['Executive Summary', 'Insights', 'Planning', 'Corrective Actions', 'Settings', 'All Teams', 'Inbound', 'CSR']) {
      expect(screen.queryByRole('link', { name })).not.toBeInTheDocument();
    }
    expect(screen.queryByText('Shared Functions')).not.toBeInTheDocument();
    expect(screen.queryByText('Employee')).not.toBeInTheDocument();
    expect(screen.getByText('Read-only')).toHaveAttribute('title', 'Function Viewer');
  });

  it('shows no function links when /auth/me has no accessible_functions', async () => {
    authState.user = { ...authState.user, accessible_functions: undefined };
    renderSidebar('/function-summary/call-center');
    expect(await screen.findByRole('link', { name: 'Function Summary' })).toBeInTheDocument();
    for (const name of ['Call Center', 'RCM', 'Pre-Approvals', 'Marketing']) {
      expect(screen.queryByRole('link', { name })).not.toBeInTheDocument();
    }
  });
});

describe('new role navigation boundaries', () => {
  beforeEach(() => {
    mockTeamConfigFetch();
    catalogState.scopes = DEFAULT_SCOPES;
  });

  it('keeps Employee navigation self-only and hides Settings', () => {
    authState.user = {
      id: 'employee-user', name: 'Eli Employee', username: 'eli', role: 'Employee',
      employee_id: 'E-100', accessible_teams: [],
    };
    renderSidebar();

    expect(screen.getByRole('link', { name: 'My Profile' })).toHaveAttribute('href', '/employee/E-100');
    for (const name of ['Executive Summary', 'All Teams', 'Reports', 'Insights', 'Planning', 'Corrective Actions', 'Settings']) {
      expect(screen.queryByRole('link', { name })).not.toBeInTheDocument();
    }
  });

  it('shows Function Director summary and scoped teams, not performance workspaces', () => {
    authState.user = {
      id: 'function-director', name: 'Fiona Director', username: 'fiona', role: 'Function Director',
      accessible_teams: [], accessible_functions: ['Marketing'],
    };
    renderSidebar();

    for (const name of ['All Teams', 'Reports', 'Insights', 'Planning', 'Corrective Actions']) {
      expect(screen.queryByRole('link', { name })).not.toBeInTheDocument();
    }
    expect(screen.queryByRole('link', { name: 'Function Summary' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Employee teams' })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('link', { name: 'Marketing' })).toHaveAttribute('href', '/team/marketing?performance_level=Employee');
    expect(screen.queryByText('FUNCTION VIEWER')).not.toBeInTheDocument();
  });

  it.each(['Branch Director', 'Regional Manager'] as const)('uses the server-scoped catalog for %s rather than empty team assignments', (role) => {
    authState.user = { id: 'director', username: 'director', name: 'Director', role, accessible_teams: [], accessible_branches: ['dubai'], accessible_regions: ['UAE'] };
    catalogState.scopes = [{ team: 'Pre-Approvals OP Dubai', region: 'UAE', performance_level: 'Employee', position: '' }];
    renderSidebar('/executive?branch=sharjah&region=EGY');
    const href = screen.getByRole('link', { name: 'Pre-Approvals OP Final' }).getAttribute('href')!;
    expect(href).toContain('/team/pre-approvals-op-final');
    expect(href).toContain(role === 'Branch Director' ? 'branch=dubai' : 'region=UAE');
    expect(screen.queryByRole('link', { name: 'Marketing' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Function Summary' })).not.toBeInTheDocument();
    for (const level of ['Managerial', 'Corporate']) expect(screen.queryByRole('button', { name: `${level} teams` })).not.toBeInTheDocument();
    for (const name of ['All Teams', 'Reports', 'Insights', 'Planning', 'Corrective Actions']) expect(screen.queryByRole('link', { name })).not.toBeInTheDocument();
  });

  it.each(['Branch Director', 'Regional Manager', 'Function Director'] as const)('groups authorized team names by level for %s and preserves scoped drilldowns', (role) => {
    authState.user = { id: 'director', username: 'director', name: 'Director', role, accessible_teams: [], accessible_branches: ['dubai'], accessible_regions: ['UAE'], accessible_functions: ['RCM'] };
    catalogState.scopes = [
      { team: 'Coding', region: 'UAE', performance_level: 'Employee', position: '' },
      { team: 'Coding', region: 'UAE', performance_level: 'Employee', position: 'Agent' },
      { team: 'Coding', region: 'UAE', performance_level: 'Managerial', position: '' },
      { team: 'Coding', region: 'UAE', performance_level: 'Corporate', position: '' },
    ];
    renderSidebar('/team/coding?performance_level=Corporate&branch=sharjah&region=EGY');
    expect(screen.queryByRole('link', { name: 'Function Summary' })).not.toBeInTheDocument();
    expect(screen.queryByText('Your teams')).not.toBeInTheDocument();
    for (const level of ['Employee', 'Managerial', 'Corporate']) {
      const toggle = screen.getByRole('button', { name: `${level} teams` });
      if (toggle.getAttribute('aria-expanded') !== 'true') fireEvent.click(toggle);
      const group = screen.getByRole('group', { name: `${level} teams` });
      expect(within(group).getAllByRole('link')).toHaveLength(1);
      const link = within(group).getByRole('link', { name: 'Coding' });
      const destination = new URL(link.getAttribute('href')!, 'http://localhost');
      expect(destination.searchParams.get('performance_level')).toBe(level);
      if (role === 'Branch Director') expect(destination.searchParams.get('branch')).toBe('dubai');
      if (role === 'Regional Manager') expect(destination.searchParams.get('region')).toBe('UAE');
      expect(link.getAttribute('aria-current')).toBe(level === 'Corporate' ? 'page' : null);
      expect(link).toHaveAttribute('title', 'Coding');
    }
    expect(screen.queryByRole('link', { name: /Coding ·/ })).not.toBeInTheDocument();
  });
});

describe('Sidebar query carry-over (QA BUG-1b)', () => {
  beforeEach(() => {
    mockTeamConfigFetch();
    authState.user = ADMIN_USER;
  });

  it.each([
    '/function-summary/rcm', '/team/coding', '/reports', '/insights',
  ])('returns to the company overview without carrying page-specific filters from %s', (path) => {
    renderSidebar(`${path}?period=2026-06&month=June&year=2026&region=All&branch=dubai&function=RCM&team=Coding&sub_team=Submission&position=Agent&level=Corporate&performance_level=Employee&employee_id=other&status=Open`);
    expect(screen.getByRole('link', { name: 'Executive Summary' })).toHaveAttribute('href', '/executive?period=2026-06&month=June&year=2026');
  });

  it.each([
    { role: 'Branch Director' as const, grant: { accessible_branches: ['dubai'] }, fixed: 'branch=dubai' },
    { role: 'Regional Manager' as const, grant: { accessible_regions: ['UAE'] }, fixed: 'region=UAE' },
  ])('keeps the $role boundary when returning to the overview', ({ role, grant, fixed }) => {
    authState.user = { id: 'director', name: 'Director', username: 'director', role, ...grant };
    renderSidebar('/team/coding?period=2026-06&region=EGY&branch=sharjah&team=Submission&level=Corporate');
    expect(screen.getByRole('link', { name: 'Executive Summary' })).toHaveAttribute('href', `/executive?period=2026-06&${fixed}`);
  });

  it('links Insights to plain /insights from a filtered Insights URL', () => {
    renderSidebar('/insights?period=2026-06&region=UAE&function=Call%20Center&team=Inbound&performance_level=Employee');

    const insights = screen.getByRole('link', { name: 'Insights' });
    expect(insights).toHaveAttribute('href', '/insights');
    expect(insights).toHaveAttribute('aria-current', 'page');
  });

  it('links Insights to plain /insights from another dashboard with a month filter', () => {
    renderSidebar('/executive?month=June&performance_level=Employee');

    expect(screen.getByRole('link', { name: 'Insights' })).toHaveAttribute('href', '/insights');
  });

  it('still carries the Header month filter to the other dashboards', () => {
    renderSidebar('/team/all?month=June');

    expect(screen.getByRole('link', { name: 'Executive Summary' })).toHaveAttribute('href', '/executive?month=June');
    expect(screen.getByRole('link', { name: 'Reports' })).toHaveAttribute('href', '/reports?month=June');
  });
});

function ResponsiveSidebarHarness() {
  const [open, setOpen] = useState(false);
  return <><button onClick={() => setOpen(true)}>Launch navigation</button><Sidebar isOpen={open} setIsOpen={setOpen} isDesktop={false} /></>;
}

describe('responsive dock and navigation drawer', () => {
  beforeEach(() => {
    authState.user = ADMIN_USER;
    catalogState.scopes = DEFAULT_SCOPES;
    mockTeamConfigFetch();
  });

  const renderResponsive = (path = '/executive') => render(
    <MemoryRouter initialEntries={[path]}><ThemeProvider><ResponsiveSidebarHarness /></ThemeProvider></MemoryRouter>,
    { wrapper: QueryWrapper },
  );

  it('shows compact permitted shortcuts and keeps the closed drawer out of the accessibility tree', () => {
    renderResponsive('/team/coding?period=2026-08&team=Coding&performance_level=Employee');
    const dock = screen.getByRole('navigation', { name: 'Quick navigation' });
    expect(within(dock).getByRole('link', { name: 'Go to Summary' })).toHaveAttribute('href', '/executive?period=2026-08');
    expect(within(dock).getByRole('link', { name: 'Go to Teams' })).toHaveAttribute('aria-current', 'page');
    expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('opens the full menu, focuses close, locks scrolling and restores focus after Escape', () => {
    renderResponsive();
    const opener = screen.getByRole('button', { name: 'Launch navigation' });
    opener.focus();
    fireEvent.click(opener);
    expect(screen.getByRole('dialog', { name: 'Navigation menu' })).toHaveAttribute('aria-modal', 'true');
    expect(screen.getByRole('button', { name: 'Close navigation sidebar' })).toHaveFocus();
    expect(document.body.style.overflow).toBe('hidden');
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe('');
    expect(opener).toHaveFocus();
  });

  it('closes from the backdrop and retains all grouped team links inside the drawer', () => {
    renderResponsive();
    const opener = screen.getByRole('button', { name: 'Open full navigation' });
    opener.focus();
    fireEvent.click(opener);
    expect(screen.getByRole('link', { name: 'Executive Summary' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Employee' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss navigation menu' }));
    expect(screen.getByRole('navigation', { name: 'Quick navigation' })).toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it.each(['Branch Director', 'Regional Manager', 'Function Director'] as const)('does not expose workspaces in the %s dock', (role) => {
    authState.user = { id: 'director', name: 'Director', username: 'director', role, accessible_branches: ['dubai'], accessible_regions: ['UAE'], accessible_functions: ['RCM'] };
    renderResponsive('/team/coding?period=2026-08&branch=sharjah&region=EGY');
    const dock = screen.getByRole('navigation', { name: 'Quick navigation' });
    expect(within(dock).getAllByRole('link').filter((link) => !link.classList.contains('navigation-dock-tablet-only'))).toHaveLength(2);
    const destination = within(dock).getByRole('link', { name: 'Go to Summary' }).getAttribute('href');
    if (role === 'Branch Director') expect(destination).toContain('branch=dubai');
    if (role === 'Regional Manager') expect(destination).toContain('region=UAE');
    for (const page of ['Reports', 'Teams', 'Insights', 'Planning']) expect(within(dock).queryByRole('link', { name: `Go to ${page}` })).not.toBeInTheDocument();
  });

  it('keeps Employee shortcuts self-only', () => {
    authState.user = { id: 'employee', name: 'Employee', username: 'employee', role: 'Employee', employee_id: 'E-100' };
    renderResponsive('/employee/E-100');
    const dock = screen.getByRole('navigation', { name: 'Quick navigation' });
    expect(within(dock).getAllByRole('link')).toHaveLength(2);
    expect(within(dock).getByRole('link', { name: 'Go to Account' })).toHaveAttribute('href', '/account');
    expect(within(dock).getByRole('link', { name: 'Go to My profile' })).toHaveAttribute('href', '/employee/E-100');
  });

  it('adds all permitted workspaces and account on tablet, while keeping three mobile shortcuts', () => {
    renderResponsive();
    const dock = screen.getByRole('navigation', { name: 'Quick navigation' });
    const links = within(dock).getAllByRole('link');
    expect(links).toHaveLength(7);
    expect(links.filter((link) => !link.classList.contains('navigation-dock-tablet-only'))).toHaveLength(3);
    for (const label of ['Insights', 'Planning', 'Actions', 'Account']) {
      expect(within(dock).getByRole('link', { name: `Go to ${label}` })).toHaveClass('navigation-dock-tablet-only');
    }
    expect(within(dock).getByRole('link', { name: 'Go to Actions' })).toHaveAttribute('href', '/corrective-actions');
    expect(within(dock).getByRole('link', { name: 'Go to Account' })).toHaveAttribute('href', '/account');
  });

  it('adds direct authorized team shortcuts for scoped directors only on tablet', () => {
    authState.user = { id: 'director', name: 'Director', username: 'director', role: 'Branch Director', accessible_branches: ['dubai'] };
    catalogState.scopes = [
      { team: 'Coding', region: 'UAE', performance_level: 'Corporate', position: '' },
      { team: 'Coding', region: 'UAE', performance_level: 'Employee', position: '' },
      { team: 'Submission', region: 'UAE', performance_level: 'Employee', position: '' },
    ];
    renderResponsive('/executive?period=2026-08&branch=sharjah');
    const dock = screen.getByRole('navigation', { name: 'Quick navigation' });
    const coding = within(dock).getByRole('link', { name: 'Go to Coding' });
    expect(coding).toHaveClass('navigation-dock-tablet-only');
    const destination = new URL(coding.getAttribute('href')!, 'http://localhost');
    expect(destination.pathname).toBe('/team/coding');
    expect(destination.searchParams.get('period')).toBe('2026-08');
    expect(destination.searchParams.get('branch')).toBe('dubai');
    expect(destination.searchParams.get('performance_level')).toBe('Employee');
    expect(within(dock).getByRole('link', { name: 'Go to Submission' })).toBeInTheDocument();
    expect(within(dock).queryByRole('link', { name: 'Go to Marketing' })).not.toBeInTheDocument();
  });

  it('keeps legacy Function Viewer shortcuts within their read-only pages', () => {
    authState.user = { id: 'viewer', name: 'Viewer', username: 'viewer', role: 'Function Viewer', accessible_functions: ['RCM'] };
    renderResponsive('/function-summary/rcm');
    const dock = screen.getByRole('navigation', { name: 'Quick navigation' });
    expect(within(dock).getByRole('link', { name: 'Go to Functions' })).toHaveAttribute('href', '/function-summary');
    expect(within(dock).queryByRole('link', { name: 'Go to My profile' })).not.toBeInTheDocument();
  });

  it.each(['Employee', 'Manager', 'Function Viewer', 'Performance Team', 'Regional Manager', 'Branch Director', 'Function Director'] as const)('gives %s Account settings instead of an administration link', role => {
    authState.user = { id: 'own-user', name: 'Own User', username: 'own', role, employee_id: 'E-100', accessible_functions: ['RCM'], accessible_branches: ['dubai'], accessible_regions: ['UAE'] };
    renderResponsive();
    const dock = screen.getByRole('navigation', { name: 'Quick navigation' });
    expect(within(dock).getByRole('link', { name: 'Go to Account' })).toHaveAttribute('href', '/account');
    fireEvent.click(screen.getByRole('button', { name: 'Open full navigation' }));
    const dialog = screen.getByRole('dialog', { name: 'Navigation menu' });
    expect(within(dialog).getByRole('link', { name: 'Account settings' })).toHaveAttribute('href', '/account');
    expect(within(dialog).queryByRole('link', { name: 'Administration' })).not.toBeInTheDocument();
  });
});
