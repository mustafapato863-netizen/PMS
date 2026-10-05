import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  role: 'Admin' | 'General Manager' | 'Manager' | 'Executive' | 'Viewer' | 'Agent';
  is_general_manager?: boolean;
  accessible_teams?: string[];
};

const authState = vi.hoisted(() => ({
  user: {
    id: 'admin-1',
    name: 'Admin',
    username: 'admin',
    role: 'Admin',
    is_general_manager: true,
    accessible_teams: [],
  } as MockUser,
}));

const ADMIN_USER: MockUser = {
  id: 'admin-1',
  name: 'Admin',
  username: 'admin',
  role: 'Admin',
  is_general_manager: true,
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
      scopes: [{
        team: 'Marketing',
        region: 'EGY',
        performance_level: 'Employee',
        position: 'Media Buyer',
      }],
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

  it('does not treat a Manager with the legacy is_general_manager flag as a General Manager', () => {
    authState.user = {
      id: 'mgr-all',
      name: 'Alma Teams',
      username: 'mgr-all',
      role: 'Manager',
      is_general_manager: true,
      accessible_teams: [],
    };
    renderSidebar();

    for (const name of ['Reports', 'Insights', 'Planning', 'Corrective Actions']) {
      expect(screen.queryByRole('link', { name })).not.toBeInTheDocument();
    }
    expect(screen.getByRole('link', { name: 'Assigned Teams' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Settings' })).toBeInTheDocument();
    expect(screen.queryByText('General Manager')).not.toBeInTheDocument();
  });

  it('keeps product pages away from a scoped Manager but still shows the soft-locked Settings link', () => {
    authState.user = {
      id: 'mgr-1',
      name: 'Mo Scoped',
      username: 'mgr',
      role: 'Manager',
      is_general_manager: false,
      accessible_teams: ['Marketing'],
    };
    renderSidebar();

    for (const name of ['Reports', 'Insights', 'Planning', 'Corrective Actions']) {
      expect(screen.queryByRole('link', { name })).not.toBeInTheDocument();
    }
    expect(screen.getByRole('link', { name: 'Settings' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Assigned Teams' })).toBeInTheDocument();
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
