import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';

import { UserManagementPanel } from './UserManagementPanel';


const mocks = vi.hoisted(() => ({
  refreshUsers: vi.fn().mockResolvedValue(undefined),
  deleteUser: vi.fn().mockResolvedValue({ success: true }),
  addUser: vi.fn().mockResolvedValue({ success: true }),
  updateUser: vi.fn().mockResolvedValue({ success: true }),
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
    updateUser: mocks.updateUser,
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

it('creates a Performance Team account using the current role set', async () => {
  const user = userEvent.setup();
  render(<UserManagementPanel />);

  await user.click(screen.getByRole('button', { name: /Add user/ }));
  await user.type(screen.getByRole('textbox', { name: 'Full name' }), 'Pat Performance');
  await user.type(screen.getByRole('textbox', { name: 'Username' }), 'Pat');
  await user.type(screen.getByLabelText(/Temporary password/), 'secret-pass');
  await user.selectOptions(screen.getByRole('combobox', { name: 'Role' }), 'Performance Team');
  await user.click(screen.getByRole('button', { name: 'Create user' }));

  await waitFor(() => expect(mocks.addUser).toHaveBeenCalledWith('Pat Performance', 'pat', 'secret-pass', 'Performance Team', [], false, [], [], []));
});

it('filters legacy roles for existing accounts without offering them for new assignments', async () => {
  render(<UserManagementPanel />);
  const filter = screen.getByRole('combobox', { name: 'Filter by role' });
  const roles = Array.from((filter as HTMLSelectElement).options).map((option) => option.value);
  expect(roles).toContain('Employee');
  expect(roles).toContain('Function Viewer');
  expect(roles).toContain('Viewer');
  await userEvent.setup().click(screen.getByRole('button', { name: /Add user/ }));
  const assignmentRoles = Array.from(screen.getByRole('combobox', { name: 'Role' }).querySelectorAll('option')).map((option) => option.value);
  expect(assignmentRoles).not.toContain('General Manager');
  expect(assignmentRoles).not.toContain('Function Viewer');
});

it('saves edited function grants through the admin panel', async () => {
  const user = userEvent.setup();
  render(<UserManagementPanel />);
  await user.click(screen.getByRole('button', { name: 'Actions for Function User' }));
  await user.click(screen.getByRole('button', { name: 'Edit' }));
  expect(screen.getByRole('checkbox', { name: 'RCM' })).toBeChecked();
  expect(screen.getByRole('checkbox', { name: 'Marketing' })).toBeChecked();
  await user.click(screen.getByRole('checkbox', { name: 'Marketing' }));
  await user.click(screen.getByRole('checkbox', { name: 'Call Center' }));
  await user.selectOptions(screen.getByRole('combobox', { name: 'Role' }), 'Function Director');
  await user.click(screen.getByRole('button', { name: 'Save changes' }));
  await waitFor(() => expect(mocks.updateUser).toHaveBeenCalledWith('functions', expect.objectContaining({
    role: 'Function Director', accessible_functions: ['RCM', 'Call Center'],
    accessible_teams: [], has_unrestricted_team_access: false,
  })));
  expect(screen.getByRole('status')).toHaveTextContent('User updated successfully.');
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

it('opens the last-row actions above the trigger when the viewport has no room below', async () => {
  const bounds = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    const trigger = this.getAttribute('aria-label')?.startsWith('Actions for');
    return { x: 900, y: trigger ? 725 : 0, left: 900, top: trigger ? 725 : 0,
      right: trigger ? 932 : 1044, bottom: trigger ? 757 : 104, width: trigger ? 32 : 144,
      height: trigger ? 32 : 104, toJSON: () => ({}) };
  });
  try {
    render(<UserManagementPanel />);
    await userEvent.setup().click(screen.getByRole('button', { name: 'Actions for Function User' }));
    const popup = screen.getByRole('button', { name: 'Edit' }).parentElement!;
    const top = Number.parseFloat(popup.style.top);
    expect(top + 104).toBeLessThanOrEqual(window.innerHeight - 8);
    expect(top + 104).toBeLessThanOrEqual(725 - 4);
  } finally {
    bounds.mockRestore();
  }
});

it.each([
  { name: 'top row', top: 50, right: 932, expectedTop: 86, expectedLeft: 788 },
  { name: 'left edge', top: 50, right: 32, expectedTop: 86, expectedLeft: 8 },
  { name: 'right edge', top: 50, right: 1100, expectedTop: 86, expectedLeft: 872 },
])('keeps actions on-screen at the $name', async ({ top, right, expectedTop, expectedLeft }) => {
  const bounds = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    const trigger = this.getAttribute('aria-label')?.startsWith('Actions for');
    return { x: right - 32, y: top, left: right - 32, top, right,
      bottom: top + 32, width: trigger ? 32 : 144, height: trigger ? 32 : 104, toJSON: () => ({}) };
  });
  try {
    render(<UserManagementPanel />);
    await userEvent.setup().click(screen.getByRole('button', { name: 'Actions for Function User' }));
    const popup = screen.getByRole('group', { name: 'User actions' });
    expect(Number.parseFloat(popup.style.top)).toBe(expectedTop);
    expect(Number.parseFloat(popup.style.left)).toBe(expectedLeft);
    expect(popup.style.visibility).toBe('visible');
  } finally {
    bounds.mockRestore();
  }
});

it('dismisses actions with Escape or an outside click and restores focus on Escape', async () => {
  const user = userEvent.setup();
  render(<UserManagementPanel />);
  const trigger = screen.getByRole('button', { name: 'Actions for Function User' });
  await user.click(trigger);
  expect(trigger).toHaveAttribute('aria-expanded', 'true');
  await user.keyboard('{Escape}');
  expect(screen.queryByRole('group', { name: 'User actions' })).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
  expect(trigger).toHaveAttribute('aria-expanded', 'false');
  await user.click(trigger);
  await user.click(screen.getByRole('heading', { name: 'User Management' }));
  expect(screen.queryByRole('group', { name: 'User actions' })).not.toBeInTheDocument();
});

it('closes actions when their anchor scrolls or the viewport resizes', async () => {
  const user = userEvent.setup();
  render(<UserManagementPanel />);
  const trigger = screen.getByRole('button', { name: 'Actions for Function User' });
  await user.click(trigger);
  const popup = screen.getByRole('group', { name: 'User actions' });
  act(() => popup.dispatchEvent(new Event('scroll')));
  expect(popup).toBeInTheDocument();
  act(() => trigger.closest('table')!.dispatchEvent(new Event('scroll')));
  expect(screen.queryByRole('group', { name: 'User actions' })).not.toBeInTheDocument();
  await user.click(trigger);
  act(() => window.dispatchEvent(new Event('resize')));
  expect(screen.queryByRole('group', { name: 'User actions' })).not.toBeInTheDocument();
});
