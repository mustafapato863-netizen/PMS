import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ThemeProvider } from '../../context/ThemeContext';
import { apiFetch } from '../../lib/apiClient';
import Sidebar from './Sidebar';
import { TEAM_ITEMS } from './sidebarTeamItems';

type MockUser = {
  id: string;
  name: string;
  username: string;
  role: 'Admin' | 'General Manager' | 'Manager' | 'Executive' | 'Viewer' | 'Agent' | 'Function Viewer';
  has_unrestricted_team_access?: boolean;
  accessible_teams?: string[];
  accessible_functions?: string[];
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

const renderSidebar = (initialEntry = '/') => render(
  <MemoryRouter initialEntries={[initialEntry]}>
    <ThemeProvider>
      <Sidebar isOpen setIsOpen={vi.fn()} />
    </ThemeProvider>
  </MemoryRouter>,
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
    authState.user = ADMIN_USER;
    catalogState.scopes = DEFAULT_SCOPES;
    mockTeamConfigFetch();
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
      </MemoryRouter>,
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
      </MemoryRouter>,
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

  it('gives a General Manager Reports, Insights, Planning, Corrective Actions, All Teams and the Settings link', () => {
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
    // Settings stays visible like for other non-Agent roles; SettingsView soft-locks the content.
    expect(screen.getByRole('link', { name: 'Settings' })).toBeInTheDocument();
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
    expect(screen.getByRole('link', { name: 'Settings' })).toBeInTheDocument();
    expect(screen.queryByText('General Manager')).not.toBeInTheDocument();
  });

  it('gives a scoped Manager the Executive v1 menu (no Insights) and the soft-locked Settings link', () => {
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
    expect(screen.getByRole('link', { name: 'Settings' })).toBeInTheDocument();
    expect(screen.getByText('Manager')).toBeInTheDocument();
  });

  it('still shows Settings and every product page to Admin', () => {
    authState.user = ADMIN_USER;
    renderSidebar();

    for (const name of ['Reports', 'Insights', 'Planning', 'Corrective Actions', 'Settings', 'All Teams']) {
      expect(screen.getByRole('link', { name })).toBeInTheDocument();
    }
    expect(screen.queryByText('General Manager')).not.toBeInTheDocument();
  });

  it('shows Corrective Actions and Settings but not Admin/GM product pages to Executive', () => {
    authState.user = { id: 'exec-1', name: 'Eve Exec', username: 'exec', role: 'Executive', accessible_teams: [] };
    renderSidebar();

    expect(screen.getByRole('link', { name: 'Corrective Actions' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Settings' })).toBeInTheDocument();
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
    fireEvent.click(screen.getByRole('button', { name: 'Show Pre-Approvals teams' }));
    expect(within(screen.getByRole('group', { name: 'Pre-Approvals teams' })).getByRole('link', { name: 'Pre-Approvals OP Final' })).toBeInTheDocument();
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

  it('falls back to all four functions when /auth/me has no accessible_functions', async () => {
    authState.user = { ...authState.user, accessible_functions: undefined };
    renderSidebar('/function-summary/call-center');
    await screen.findByRole('link', { name: 'Call Center' });
    for (const name of ['Call Center', 'RCM', 'Pre-Approvals', 'Marketing']) {
      expect(screen.getAllByRole('link', { name }).length).toBeGreaterThan(0);
    }
  });
});

describe('Sidebar query carry-over (QA BUG-1b)', () => {
  beforeEach(() => {
    mockTeamConfigFetch();
    authState.user = ADMIN_USER;
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
