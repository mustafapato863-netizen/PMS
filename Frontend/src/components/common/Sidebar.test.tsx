import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ThemeProvider } from '../../context/ThemeContext';
import { apiFetch } from '../../lib/apiClient';
import Sidebar from './Sidebar';
import { TEAM_ITEMS } from './sidebarTeamItems';

vi.mock('../../context/RoleContext', () => ({
  useUserRole: () => ({ role: 'Admin' }),
}));

vi.mock('../../context/auth', () => ({
  useAuth: () => ({
    currentUser: {
      id: 'admin-1',
      name: 'Admin',
      username: 'admin',
      role: 'Admin',
      is_general_manager: true,
      accessible_teams: [],
    },
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

describe('Sidebar team icons', () => {
  beforeEach(() => {
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
