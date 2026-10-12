import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import SettingsView from './SettingsView';
import { initialReportingPeriod } from '../components/settings/evaluationSettings';

const roleState = vi.hoisted(() => ({ role: 'General Manager' as string }));
// The overview's cards read through fetchWithRole. An empty, successful reply resolves every card to its empty state.
const requests = vi.hoisted(() => ({
  fetchWithRole: vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ success: true, data: [] }) })),
}));

vi.mock('../context/RoleContext', () => ({
  useUserRole: () => ({ role: roleState.role, fetchWithRole: requests.fetchWithRole }),
}));

vi.mock('../components/settings/DataManagementPanel', () => ({ DataManagementPanel: () => <p>Data management panel</p> }));
vi.mock('../components/settings/CorrectiveActionDataPanel', () => ({ CorrectiveActionDataPanel: () => <p>Corrective action panel</p> }));
vi.mock('../components/settings/EvaluationSettingsPanel', () => ({
  // The real panel reads the month from window.location on mount, so the stand-in does the same.
  EvaluationSettingsPanel: () => {
    const { year, month } = initialReportingPeriod(window.location.search);
    return <p>Evaluation settings panel {year}-{month}</p>;
  },
}));
vi.mock('../components/settings/UserManagementPanel', () => ({ UserManagementPanel: () => <p>User management panel</p> }));
vi.mock('../components/settings/SystemErrorsPanel', () => ({ SystemErrorsPanel: () => <p>System errors panel</p> }));
vi.mock('./TeamManagementView', () => ({ default: () => <p>Team management panel</p> }));

function Address() {
  const { pathname, search } = useLocation();
  return <p data-testid="address">{`${pathname}${search}`}</p>;
}

function HistoryControls() {
  const navigate = useNavigate();
  return (
    <>
      <button type="button" onClick={() => navigate(-1)}>Browser back</button>
      <button type="button" onClick={() => navigate(1)}>Browser forward</button>
    </>
  );
}

function renderAt(path: string) {
  // Evaluation settings reads its month from window.location, so the address bar is mirrored here too.
  window.history.replaceState(null, '', path);
  // A fresh client per render keeps each test's overview cache separate. Retry is off so failures surface at once.
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <HistoryControls />
        <Address />
        <Routes>
          <Route path="/settings" element={<SettingsView />} />
          <Route path="/settings/:section" element={<SettingsView />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  window.history.replaceState(null, '', '/');
});

describe('SettingsView soft-lock', () => {
  it.each(['General Manager', 'Manager', 'Executive', 'Viewer'])('shows the Administrator access required panel to %s', (role) => {
    roleState.role = role;
    renderAt('/settings');
    expect(screen.getByText('Administrator access required')).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Settings sections' })).not.toBeInTheDocument();
    expect(screen.queryByText('Data management panel')).not.toBeInTheDocument();
  });

  it.each(['/settings/users', '/settings/evaluation?year=2026&month=8', '/settings/teams'])('keeps the soft lock on the deep URL %s and does not redirect', (path) => {
    roleState.role = 'General Manager';
    renderAt(path);
    expect(screen.getByText('Administrator access required')).toBeInTheDocument();
    expect(screen.queryByText('User management panel')).not.toBeInTheDocument();
    expect(screen.queryByText(/Evaluation settings panel/)).not.toBeInTheDocument();
    expect(screen.getByTestId('address')).toHaveTextContent(path);
  });

  it('renders the admin panels for Admin', async () => {
    roleState.role = 'Admin';
    renderAt('/settings/data');
    expect(await screen.findByText('Data management panel')).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Settings sections' })).toBeInTheDocument();
    expect(screen.queryByText('Administrator access required')).not.toBeInTheDocument();
  });
});

describe('SettingsView routing', () => {
  it('redirects /settings to the overview and keeps the query string', async () => {
    roleState.role = 'Admin';
    renderAt('/settings?year=2026&month=8');
    await waitFor(() => expect(screen.getByTestId('address').textContent).toBe('/settings/overview?year=2026&month=8'));
    expect(screen.getByRole('heading', { name: 'Areas' })).toBeInTheDocument();
  });

  it('sends a legacy tab shortcut to its section', async () => {
    roleState.role = 'Admin';
    renderAt('/settings?tab=users');
    await waitFor(() => expect(screen.getByTestId('address').textContent).toBe('/settings/users?tab=users'));
    expect(await screen.findByText('User management panel')).toBeInTheDocument();
  });

  it.each([
    ['/settings/data', 'Data management panel'],
    ['/settings/corrective-actions', 'Corrective action panel'],
    ['/settings/evaluation?year=2026&month=8', 'Evaluation settings panel 2026-8'],
    ['/settings/users', 'User management panel'],
    ['/settings/system-errors', 'System errors panel'],
  ])('renders the panel for %s', async (path, text) => {
    roleState.role = 'Admin';
    renderAt(path);
    expect(await screen.findByText(text)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Areas' })).not.toBeInTheDocument();
  });

  it('opens Evaluation settings on the month named in the address', async () => {
    roleState.role = 'Admin';
    renderAt('/settings/evaluation?year=2026&month=8');
    expect(await screen.findByText('Evaluation settings panel 2026-8')).toBeInTheDocument();
    expect(screen.getByTestId('address').textContent).toBe('/settings/evaluation?year=2026&month=8');
  });

  it('opens the overview for an unknown slug and keeps the query string', async () => {
    roleState.role = 'Admin';
    renderAt('/settings/not-a-section?year=2026&month=8');
    await waitFor(() => expect(screen.getByTestId('address').textContent).toBe('/settings/overview?year=2026&month=8'));
    expect(screen.getByRole('heading', { name: 'Areas' })).toBeInTheDocument();
  });

  it('keeps the teams section unreachable by URL', async () => {
    roleState.role = 'Admin';
    renderAt('/settings/teams');
    await waitFor(() => expect(screen.getByTestId('address').textContent).toBe('/settings/overview'));
    expect(screen.queryByText('Team management panel')).not.toBeInTheDocument();
  });

  it('shows the Administration page header above the panels', async () => {
    roleState.role = 'Admin';
    renderAt('/settings/data');
    expect(await screen.findByRole('heading', { level: 1, name: 'Administration' })).toBeInTheDocument();
  });

  it('changes the section and the address when a navigation item is clicked', async () => {
    roleState.role = 'Admin';
    renderAt('/settings/data');
    const nav = await screen.findByRole('navigation', { name: 'Settings sections' });
    await userEvent.click(within(nav).getByRole('link', { name: 'Users' }));
    expect(screen.getByTestId('address').textContent).toBe('/settings/users');
    expect(await screen.findByText('User management panel')).toBeInTheDocument();
    expect(screen.queryByText('Data management panel')).not.toBeInTheDocument();
  });

  it('moves between sections with browser back and forward', async () => {
    roleState.role = 'Admin';
    renderAt('/settings/data');
    const nav = await screen.findByRole('navigation', { name: 'Settings sections' });
    await userEvent.click(within(nav).getByRole('link', { name: 'Users' }));
    expect(await screen.findByText('User management panel')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Browser back' }));
    expect(await screen.findByText('Data management panel')).toBeInTheDocument();
    expect(screen.getByTestId('address').textContent).toBe('/settings/data');

    await userEvent.click(screen.getByRole('button', { name: 'Browser forward' }));
    expect(await screen.findByText('User management panel')).toBeInTheDocument();
    expect(screen.getByTestId('address').textContent).toBe('/settings/users');
  });
});
