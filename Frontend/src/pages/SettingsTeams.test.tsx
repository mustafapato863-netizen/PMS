import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import SettingsView from './SettingsView';

const roleState = vi.hoisted(() => ({ role: 'Admin' as string }));
const requests = vi.hoisted(() => ({
  fetchWithRole: vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ success: true, data: [] }) })),
}));

vi.mock('../context/RoleContext', () => ({
  useUserRole: () => ({ role: roleState.role, fetchWithRole: requests.fetchWithRole }),
}));
vi.mock('./TeamManagementView', () => ({ default: () => <p>Team management panel</p> }));

function Address() {
  const { pathname } = useLocation();
  return <p data-testid="address">{pathname}</p>;
}

function renderAt(path: string) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/settings/:section" element={<SettingsView />} />
        </Routes>
        <Address />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Teams in Administration', () => {
  it('renders the team management view at /settings/teams with Teams as the current page', async () => {
    roleState.role = 'Admin';
    renderAt('/settings/teams');

    expect(await screen.findByText('Team management panel')).toBeInTheDocument();
    expect(screen.getByTestId('address')).toHaveTextContent('/settings/teams');
    const nav = screen.getByRole('navigation', { name: 'Settings sections' });
    expect(within(nav).getByRole('link', { name: 'Teams' })).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('link', { name: 'Users' })).not.toHaveAttribute('aria-current');
  });

  it('keeps the Access nav item pointing at /settings/teams', async () => {
    roleState.role = 'Admin';
    renderAt('/settings/teams');
    const nav = await screen.findByRole('navigation', { name: 'Settings sections' });
    expect(within(nav).getByRole('link', { name: 'Teams' })).toHaveAttribute('href', '/settings/teams');
  });
});
