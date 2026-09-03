import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';

import { UserManagementPanel } from './UserManagementPanel';


const mocks = vi.hoisted(() => ({
  refreshUsers: vi.fn().mockResolvedValue(undefined),
  deleteUser: vi.fn().mockResolvedValue({ success: true }),
  fetchWithRole: vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ data: [] }),
  }),
}));

vi.mock('../../context/auth', () => ({
  useAuth: () => ({
    users: [
      { id: 'online', name: 'Online Person', username: 'online', role: 'Manager', is_active: true, is_online: true },
      { id: 'offline', name: 'Offline Person', username: 'offline', role: 'Viewer', is_active: true, is_online: false, last_seen_at: '2026-07-27T12:00:00Z' },
      { id: 'never', name: 'Never Seen Person', username: 'never', role: 'Viewer', is_active: true, is_online: false, last_seen_at: null },
    ],
    currentUser: { id: 'admin', name: 'Admin', username: 'admin', role: 'Admin' },
    addUser: vi.fn(),
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
  expect(screen.getByRole('columnheader', { name: 'Presence' })).toBeInTheDocument();
  expect(screen.getByText('Online Person')).toBeInTheDocument();
  expect(screen.getByText('Offline Person')).toBeInTheDocument();
  expect(screen.getByText(/Last seen .* ago/)).toBeInTheDocument();
  expect(screen.getByText('Never seen')).toBeInTheDocument();

  await user.selectOptions(screen.getByRole('combobox', { name: 'Filter by presence' }), 'Offline');

  expect(screen.queryByText('Online Person')).not.toBeInTheDocument();
  expect(screen.getByText('Offline Person')).toBeInTheDocument();
  expect(screen.getByText('Never Seen Person')).toBeInTheDocument();
});

it('requires confirmation before deleting a user and reports success', async () => {
  const user = userEvent.setup();
  render(<UserManagementPanel />);

  await user.click(screen.getByRole('button', { name: 'Actions for Offline Person' }));
  await user.click(screen.getByRole('button', { name: 'Delete' }));

  expect(screen.getByRole('alertdialog', { name: 'Delete user?' })).toBeInTheDocument();
  expect(mocks.deleteUser).not.toHaveBeenCalled();

  await user.click(screen.getByRole('button', { name: 'Delete user' }));

  await waitFor(() => expect(mocks.deleteUser).toHaveBeenCalledWith('offline'));
  expect(screen.getByRole('status')).toHaveTextContent('User deleted successfully.');
});
