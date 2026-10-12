import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { UserManagementPanel } from './UserManagementPanel';

// 64 users in a scrambled received order, so sorting visibly changes the rows. Names and usernames are permutations.
const mocks = vi.hoisted(() => {
  const roles = ['Viewer', 'Manager', 'Employee'];
  const users = Array.from({ length: 64 }, (_, index) => {
    const name = (index * 17) % 64 + 1;
    const username = (index * 29) % 64;
    const online = index % 5 === 0;
    return {
      id: `user-${index}`,
      name: `Member ${String(name).padStart(2, '0')}`,
      username: `u-${String(username).padStart(2, '0')}`,
      role: roles[index % 3],
      is_active: index % 4 !== 0,
      is_online: online,
      last_seen_at: online ? null : new Date(Date.now() - (index + 1) * 86_400_000).toISOString(),
    };
  });
  return {
    users,
    refreshUsers: vi.fn().mockResolvedValue(undefined),
    fetchWithRole: vi.fn().mockResolvedValue({ ok: true, json: async () => ({ data: [] }) }),
  };
});

vi.mock('../../context/auth', () => ({
  useAuth: () => ({
    users: mocks.users,
    currentUser: { id: 'admin', name: 'Admin', username: 'admin', role: 'Admin' },
    addUser: vi.fn(),
    updateUser: vi.fn(),
    deleteUser: vi.fn(),
    toggleUserActive: vi.fn(),
    refreshUsers: mocks.refreshUsers,
  }),
}));

vi.mock('../../context/RoleContext', () => ({
  useUserRole: () => ({ fetchWithRole: mocks.fetchWithRole }),
}));

/** The name shown in each rendered row, in display order. */
function rowNames(): string[] {
  return screen.getAllByRole('row').slice(1).map((row) => row.querySelector('td span.font-bold')?.textContent ?? '');
}

function firstRowText(): string {
  return screen.getAllByRole('row')[1].textContent ?? '';
}

const RECEIVED_FIRST = mocks.users[0].name;

describe('Users default order and paging', () => {
  it('keeps the received order until a header is clicked', () => {
    render(<UserManagementPanel />);
    expect(rowNames()[0]).toBe(RECEIVED_FIRST);
    expect(screen.getByRole('columnheader', { name: 'User' })).toHaveAttribute('aria-sort', 'none');
  });

  it('shows 25 rows per page with the range and the total', () => {
    render(<UserManagementPanel />);
    expect(rowNames()).toHaveLength(25);
    expect(screen.getByText('Showing 1–25 of 64')).toBeInTheDocument();
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument();
  });

  it('moves between pages and disables the ends', async () => {
    const user = userEvent.setup();
    render(<UserManagementPanel />);
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByText('Showing 26–50 of 64')).toBeInTheDocument();
    expect(rowNames()).toHaveLength(25);
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByText('Showing 51–64 of 64')).toBeInTheDocument();
    expect(rowNames()).toHaveLength(14);
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });
});

describe('Users sorting', () => {
  it('sorts by User across every page, so page 1 holds the first names overall', async () => {
    const user = userEvent.setup();
    render(<UserManagementPanel />);
    await user.click(screen.getByRole('button', { name: 'User' }));
    expect(screen.getByRole('columnheader', { name: 'User' })).toHaveAttribute('aria-sort', 'ascending');
    expect(rowNames()[0]).toBe('Member 01');
    expect(rowNames()[24]).toBe('Member 25');
  });

  it('sorts Username descending, applied before paging', async () => {
    const user = userEvent.setup();
    render(<UserManagementPanel />);
    await user.click(screen.getByRole('button', { name: 'Username' }));
    await user.click(screen.getByRole('button', { name: 'Username' }));
    expect(screen.getByRole('columnheader', { name: 'Username' })).toHaveAttribute('aria-sort', 'descending');
    expect(firstRowText()).toContain('@u-63');
  });

  it('sorts Role ascending', async () => {
    const user = userEvent.setup();
    render(<UserManagementPanel />);
    await user.click(screen.getByRole('button', { name: 'Role' }));
    expect(firstRowText()).toContain('Employee');
  });

  it('sorts Account so active accounts come first when ascending', async () => {
    const user = userEvent.setup();
    render(<UserManagementPanel />);
    await user.click(screen.getByRole('button', { name: 'Account' }));
    expect(screen.getAllByRole('row')[1].textContent).toContain('Active');
    expect(screen.getByRole('columnheader', { name: 'Account' })).toHaveAttribute('aria-sort', 'ascending');
  });

  it('sorts Presence so online users come first when descending', async () => {
    const user = userEvent.setup();
    render(<UserManagementPanel />);
    await user.click(screen.getByRole('button', { name: 'Presence' }));
    await user.click(screen.getByRole('button', { name: 'Presence' }));
    expect(screen.getByRole('columnheader', { name: 'Presence' })).toHaveAttribute('aria-sort', 'descending');
    expect(firstRowText()).toContain('Online');
  });

  it('returns to the received order after the third click on the same header', async () => {
    const user = userEvent.setup();
    render(<UserManagementPanel />);
    await user.click(screen.getByRole('button', { name: 'User' }));
    await user.click(screen.getByRole('button', { name: 'User' }));
    await user.click(screen.getByRole('button', { name: 'User' }));
    expect(rowNames()[0]).toBe(RECEIVED_FIRST);
  });

  it('does not sort Access scope or Actions', () => {
    render(<UserManagementPanel />);
    expect(screen.getByRole('columnheader', { name: 'Access scope' })).not.toHaveAttribute('aria-sort');
    expect(within(screen.getByRole('table', { name: 'Users' })).queryByRole('button', { name: 'Access scope' })).not.toBeInTheDocument();
  });
});

describe('Users paging resets', () => {
  it('returns to page 1 when the search changes, even when the matches still fill several pages', async () => {
    const user = userEvent.setup();
    render(<UserManagementPanel />);
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByText('Showing 26–50 of 64')).toBeInTheDocument();
    await user.type(screen.getByRole('textbox', { name: 'Search users' }), 'u');
    expect(screen.getByText('Showing 1–25 of 64')).toBeInTheDocument();
  });

  it('returns to page 1 when a filter changes, even when the filtered rows still fill several pages', async () => {
    const user = userEvent.setup();
    render(<UserManagementPanel />);
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByText('Showing 26–50 of 64')).toBeInTheDocument();
    await user.selectOptions(screen.getByRole('combobox', { name: 'Filter by presence' }), 'Offline');
    expect(screen.getByText('Showing 1–25 of 51')).toBeInTheDocument();
  });

  it('hides the pager when the filtered rows fit on one page', async () => {
    const user = userEvent.setup();
    render(<UserManagementPanel />);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Filter by role' }), 'Manager');
    expect(screen.queryByRole('navigation', { name: 'Users pages' })).not.toBeInTheDocument();
  });

  it('returns to page 1 when the sort changes', async () => {
    const user = userEvent.setup();
    render(<UserManagementPanel />);
    await user.click(screen.getByRole('button', { name: 'Next' }));
    await user.click(screen.getByRole('button', { name: 'Role' }));
    expect(screen.getByText('Showing 1–25 of 64')).toBeInTheDocument();
  });

  it('keeps Actions working on a sorted page', async () => {
    const user = userEvent.setup();
    render(<UserManagementPanel />);
    await user.click(screen.getByRole('button', { name: 'User' }));
    await user.click(screen.getByRole('button', { name: 'Actions for Member 01' }));
    expect(screen.getByRole('group', { name: 'User actions' })).toBeInTheDocument();
  });
});
