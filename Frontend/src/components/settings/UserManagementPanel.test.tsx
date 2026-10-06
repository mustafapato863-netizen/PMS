import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';

import { UserManagementPanel } from './UserManagementPanel';


const mocks = vi.hoisted(() => ({
  refreshUsers: vi.fn().mockResolvedValue(undefined),
  deleteUser: vi.fn().mockResolvedValue({ success: true }),
  addUser: vi.fn().mockResolvedValue({ success: true }),
  fetchWithRole: vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ data: [] }),
  }),
  timestampDaysAgo: (days: number) => new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString(),
}));

vi.mock('../../context/auth', () => ({
  useAuth: () => ({
    users: [
      { id: 'online', name: 'Online Person', username: 'online', role: 'Manager', is_active: true, is_online: true },
      { id: 'seven-days', name: 'Seven Days Offline', username: 'seven-days', role: 'Viewer', is_active: true, is_online: false, last_seen_at: mocks.timestampDaysAgo(7) },
      { id: 'one-day', name: 'One Day Offline', username: 'one-day', role: 'Viewer', is_active: true, is_online: false, last_seen_at: mocks.timestampDaysAgo(1) },
      { id: 'twenty-two-days', name: 'Twenty Two Days Offline', username: 'twenty-two-days', role: 'Viewer', is_active: true, is_online: false, last_seen_at: mocks.timestampDaysAgo(22) },
      { id: 'two-months', name: 'Two Months Offline', username: 'two-months', role: 'Viewer', is_active: true, is_online: false, last_seen_at: mocks.timestampDaysAgo(62) },
      { id: 'never', name: 'Never Seen Person', username: 'never', role: 'Viewer', is_active: true, is_online: false, last_seen_at: null },
      { id: 'functions', name: 'Function User', username: 'functions', role: 'Function Viewer', accessible_functions: ['RCM', 'Marketing'], is_active: true, is_online: false, last_seen_at: mocks.timestampDaysAgo(3) },
    ],
    currentUser: { id: 'admin', name: 'Admin', username: 'admin', role: 'Admin' },
    addUser: mocks.addUser,
    updateUser: vi.fn(),
    deleteUser: mocks.deleteUser,
    toggleUserActive: vi.fn(),
    refreshUsers: mocks.refreshUsers,
  }),
}));

vi.mock('../../context/RoleContext', () => ({
  useUserRole: () => ({ fetchWithRole: mocks.fetchWithRole }),
}));


it('shows presence independently from account status and filters by it', async () => {
  const user = userEvent.setup();
  render(<UserManagementPanel />);

  expect(screen.getByRole('columnheader', { name: 'Account' })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: 'Access scope' })).toBeInTheDocument();
  expect(screen.getByText('RCM, Marketing')).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: 'Presence' })).toBeInTheDocument();
  expect(screen.getByText('Online Person')).toBeInTheDocument();
  expect(screen.getByText('Seven Days Offline')).toBeInTheDocument();
  expect(screen.getByText('One Day Offline')).toBeInTheDocument();
  expect(screen.getByText('Twenty Two Days Offline')).toBeInTheDocument();
  expect(screen.getByText('Two Months Offline')).toBeInTheDocument();
  expect(screen.getByText(/Last seen 7 days ago/)).toBeInTheDocument();
  expect(screen.getByText(/Last seen 1 day ago/)).toBeInTheDocument();
  expect(screen.getByText(/Last seen 22 days ago/)).toBeInTheDocument();
  expect(screen.getByText(/Last seen .*2 months ago/)).toBeInTheDocument();
  expect(screen.getByText('Never seen')).toBeInTheDocument();

  await user.selectOptions(screen.getByRole('combobox', { name: 'Filter by presence' }), 'Offline');

  expect(screen.queryByText('Online Person')).not.toBeInTheDocument();
  expect(screen.getByText('Seven Days Offline')).toBeInTheDocument();
  expect(screen.getByText('Never Seen Person')).toBeInTheDocument();
});

it('requires confirmation before deleting a user and reports success', async () => {
  const user = userEvent.setup();
  render(<UserManagementPanel />);

  await user.click(screen.getByRole('button', { name: 'Actions for Seven Days Offline' }));
  await user.click(screen.getByRole('button', { name: 'Delete' }));

  expect(screen.getByRole('alertdialog', { name: 'Delete user?' })).toBeInTheDocument();
  expect(mocks.deleteUser).not.toHaveBeenCalled();

  await user.click(screen.getByRole('button', { name: 'Delete user' }));

  await waitFor(() => expect(mocks.deleteUser).toHaveBeenCalledWith('seven-days'));
  expect(screen.getByRole('status')).toHaveTextContent('User deleted successfully.');
});

it('creates a General Manager with the role string, no per-team list and the all-teams flag', async () => {
  const user = userEvent.setup();
  render(<UserManagementPanel />);

  await user.click(screen.getByRole('button', { name: /Add user/ }));
  await user.type(screen.getByRole('textbox', { name: 'Full name' }), 'Gina Grant');
  await user.type(screen.getByRole('textbox', { name: 'Username' }), 'Gina');
  await user.type(screen.getByLabelText(/Password/), 'secret-pass');
  await user.selectOptions(screen.getByRole('combobox', { name: 'Role' }), 'General Manager');
  await user.click(screen.getByRole('button', { name: 'Create user' }));

  await waitFor(() => expect(mocks.addUser).toHaveBeenCalledWith('Gina Grant', 'gina', 'secret-pass', 'General Manager', [], true, []));
});

it('lists General Manager in the role filter', () => {
  render(<UserManagementPanel />);
  const filter = screen.getByRole('combobox', { name: 'Filter by role' });
  expect(Array.from((filter as HTMLSelectElement).options).map((option) => option.value)).toContain('General Manager');
  expect(Array.from((filter as HTMLSelectElement).options).map((option) => option.value)).toContain('Function Viewer');
});

it('refreshes presence while User Management is open', async () => {
  vi.useFakeTimers();
  mocks.refreshUsers.mockClear();
  try {
    render(<UserManagementPanel />);

    await act(async () => { await Promise.resolve(); });
    expect(mocks.refreshUsers).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(mocks.refreshUsers).toHaveBeenCalledTimes(2);
  } finally {
    vi.useRealTimers();
  }
});
