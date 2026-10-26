import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { formatDistanceToNow } from 'date-fns';
import { Download, MoreHorizontal, Plus, Search, Users } from 'lucide-react';
import { API_BASE } from '../../config';
import { useAuth } from '../../context/auth';
import { useUserRole } from '../../context/RoleContext';
import type { User } from '../../types';
import type { TeamConfigItem } from './types';
import { UserFormModal, type UserFormValue } from './UserFormModal';
import { USER_BRANCH_OPTIONS, USER_ROLE_OPTIONS, readHasUnrestrictedTeamAccess } from '../../lib/access';
import { safeUserName, userInitials } from './settingsUtils';
import { AdminTableShell, TableEmptyRow } from './shell/AdminTableShell';
import { BODY_CELL_CLASS, BODY_ROW_CLASS, HEAD_CELL_CLASS } from './shell/adminTableClasses';
import { SortableHeaderCell } from './shell/SortableHeaderCell';
import { TablePagination } from './shell/TablePagination';
import { usePagination } from './shell/usePagination';
import { directionFor, useTableSort, type SortColumn } from './shell/useTableSort';

const USERS_PER_PAGE = 25;

const FILTER_SELECT =
  'rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-3 py-2 text-xs font-semibold text-[var(--text-secondary)]';

type UserSortKey = 'name' | 'username' | 'role' | 'account' | 'presence';

/** Presence sorts by recent activity: online users first, then the most recently seen. Never seen sorts last. */
function presenceValue(user: User): number | null {
  if (user?.is_online) return Number.POSITIVE_INFINITY;
  if (!user?.last_seen_at) return null;
  const seen = Date.parse(user.last_seen_at);
  return Number.isNaN(seen) ? null : seen;
}

/** The sortable columns. Access scope and Actions are not sortable. */
const USER_SORT_COLUMNS: SortColumn<User, UserSortKey>[] = [
  { key: 'name', value: (user) => safeUserName(user) },
  { key: 'username', value: (user) => user?.username || null },
  { key: 'role', value: (user) => user?.role || null },
  { key: 'account', value: (user) => ((user?.is_active ?? true) ? 'Active' : 'Disabled') },
  { key: 'presence', value: (user) => presenceValue(user) },
];

function lastSeenText(value?: string | null) {
  if (!value) return 'Never seen';
  const lastSeen = new Date(value);
  if (Number.isNaN(lastSeen.getTime())) return 'Never seen';
  return `Last seen ${formatDistanceToNow(lastSeen, { addSuffix: true })}`;
}

function accessScopeText(user: User): string {
  if (user.role === 'Admin' || user.role === 'General Manager' || user.role === 'Performance Team')
    return 'All branches and functions';
  if (user.role === 'Manager') {
    if (readHasUnrestrictedTeamAccess(user)) return 'All branches';
    return user.accessible_teams?.length ? user.accessible_teams.join(', ') : 'No branches assigned';
  }
  if (user.role === 'Function Viewer' || user.role === 'Function Director') {
    return user.accessible_functions?.length ? user.accessible_functions.join(', ') : 'No functions assigned';
  }
  if (user.role === 'Regional Manager')
    return user.accessible_regions?.length ? user.accessible_regions.join(', ') : 'No regions assigned';
  if (user.role === 'Branch Director') {
    const labels = new Map(USER_BRANCH_OPTIONS.map((branch) => [branch.key, branch.label]));
    return user.accessible_branches?.length
      ? user.accessible_branches
          .map((key) => labels.get(key as (typeof USER_BRANCH_OPTIONS)[number]['key']) || key)
          .join(', ')
      : 'No branches assigned';
  }
  if (user.role === 'Employee' || user.role === 'Agent') return 'Own employee profile';
  return user.role === 'Executive' ? 'Self only' : 'Role based';
}

function UserActionsPopover({
  trigger,
  onClose,
  children,
}: {
  trigger: HTMLButtonElement;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const popup = ref.current;
    if (!popup) return;
    const margin = 8;
    const gap = 4;
    const anchor = trigger.getBoundingClientRect();
    const menu = popup.getBoundingClientRect();
    const height = Math.min(menu.height, Math.max(0, window.innerHeight - margin * 2));
    const below = window.innerHeight - margin - anchor.bottom - gap;
    const above = anchor.top - margin - gap;
    const preferredTop =
      below >= height || below >= above ? anchor.bottom + gap : anchor.top - gap - height;
    popup.style.top = `${Math.max(margin, Math.min(preferredTop, window.innerHeight - margin - height))}px`;
    popup.style.left = `${Math.max(margin, Math.min(anchor.right - menu.width, window.innerWidth - margin - menu.width))}px`;
    popup.style.visibility = 'visible';
  }, [trigger]);

  useEffect(() => {
    const dismissOutside = (event: PointerEvent) => {
      if (
        event.target instanceof Node &&
        !ref.current?.contains(event.target) &&
        !trigger.contains(event.target)
      )
        onClose();
    };
    const dismissEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
        trigger.focus();
      }
    };
    document.addEventListener('pointerdown', dismissOutside);
    document.addEventListener('keydown', dismissEscape);
    return () => {
      document.removeEventListener('pointerdown', dismissOutside);
      document.removeEventListener('keydown', dismissEscape);
    };
  }, [trigger, onClose]);

  return createPortal(
    <div
      ref={ref}
      role="group"
      aria-label="User actions"
      style={{
        visibility: 'hidden',
        maxHeight: 'calc(100dvh - 16px)',
        maxWidth: 'calc(100vw - 16px)',
      }}
      className="fixed z-[9999] w-36 overflow-y-auto rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] py-1 text-left shadow-xl"
    >
      {children}
    </div>,
    document.body,
  );
}

export function UserManagementPanel() {
  const { users, currentUser, addUser, updateUser, deleteUser, toggleUserActive, refreshUsers } = useAuth();
  const { fetchWithRole } = useUserRole();
  const [teams, setTeams] = useState<TeamConfigItem[]>([]);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('All');
  const [presenceFilter, setPresenceFilter] = useState('All');
  const [accountFilter, setAccountFilter] = useState('All');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [menuState, setMenuState] = useState<{ userId: string; trigger: HTMLButtonElement } | null>(null);
  const closeMenu = useCallback(() => setMenuState(null), []);
  const [busy, setBusy] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<User | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const load = useCallback(async () => {
    await refreshUsers();
    const response = await fetchWithRole(`${API_BASE}/api/config/teams`);
    if (!response.ok) return;
    const result = await response.json();
    setTeams(
      (Array.isArray(result?.data) ? result.data : [])
        .map((item: unknown) => {
          const record = typeof item === 'object' && item !== null ? (item as Record<string, unknown>) : {};
          return { name: String(record.name ?? record.db_name ?? item ?? '') };
        })
        .filter((item: TeamConfigItem) => item.name),
    );
  }, [fetchWithRole, refreshUsers]);

  useEffect(() => {
    void Promise.resolve()
      .then(load)
      .catch((caught) => setError(caught instanceof Error ? caught.message : 'Failed to load users'));
  }, [load]);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      void refreshUsers();
    }, 30_000);
    return () => window.clearInterval(intervalId);
  }, [refreshUsers]);

  // Close menu on scroll or resize
  useEffect(() => {
    if (!menuState) return;
    const handleClose = (event: Event) => {
      // A short viewport can make the popup itself scrollable.
      if (
        event.type === 'scroll' &&
        event.target instanceof Element &&
        event.target.closest('[aria-label="User actions"]')
      )
        return;
      closeMenu();
    };
    window.addEventListener('scroll', handleClose, true);
    window.addEventListener('resize', handleClose);
    return () => {
      window.removeEventListener('scroll', handleClose, true);
      window.removeEventListener('resize', handleClose);
    };
  }, [menuState, closeMenu]);

  const userStats = useMemo(() => {
    const list = Array.isArray(users) ? users : [];
    let onlineCount = 0;
    let activeCount = 0;
    let disabledCount = 0;
    let reassignCount = 0;
    for (const u of list) {
      if (u?.is_online) onlineCount += 1;
      if (u?.is_active ?? true) activeCount += 1;
      else disabledCount += 1;
      if (u?.legacy_role_needs_reassignment) reassignCount += 1;
    }
    return { total: list.length, onlineCount, activeCount, disabledCount, reassignCount };
  }, [users]);

  const filteredUsers = useMemo(() => {
    const term = search.trim().toLowerCase();
    return (Array.isArray(users) ? users : []).filter((user) => {
      const name = typeof user?.name === 'string' ? user.name : '';
      const username = typeof user?.username === 'string' ? user.username : '';
      const matchesSearch =
        !term || name.toLowerCase().includes(term) || username.toLowerCase().includes(term);
      const matchesRole = roleFilter === 'All' || user?.role === roleFilter;
      const matchesPresence =
        presenceFilter === 'All' || (presenceFilter === 'Online' ? user?.is_online : !user?.is_online);
      const isActive = user?.is_active ?? true;
      const matchesAccount =
        accountFilter === 'All' ||
        (accountFilter === 'Active' && isActive) ||
        (accountFilter === 'Disabled' && !isActive) ||
        (accountFilter === 'Reassign' && Boolean(user?.legacy_role_needs_reassignment));
      return matchesSearch && matchesRole && matchesPresence && matchesAccount;
    });
  }, [users, search, roleFilter, presenceFilter, accountFilter]);

  const roleFilterOptions = useMemo(
    () => [...new Set([...USER_ROLE_OPTIONS, ...users.map((user) => user.role)])],
    [users],
  );

  const submit = async (value: UserFormValue) => {
    setBusy(true);
    setError(null);
    setSuccess(null);
    const username = value.username.trim().toLowerCase();
    // General Manager is all-branches: send no per-branch list and set has_unrestricted_team_access.
    const isGeneralManagerRole = value.role === 'General Manager';
    const hasUnrestrictedTeamAccess =
      isGeneralManagerRole || (value.role === 'Manager' && value.isGeneralManager);
    const accessibleFunctions =
      value.role === 'Function Viewer' || value.role === 'Function Director'
        ? value.accessibleFunctions
        : [];
    const result = editingUser
      ? await updateUser(editingUser.id, {
          name: value.name.trim(),
          username,
          new_password: value.password.trim() || undefined,
          role: value.role,
          is_active: editingUser.is_active ?? true,
          accessible_teams: value.role === 'Manager' ? value.accessibleTeams : [],
          has_unrestricted_team_access: hasUnrestrictedTeamAccess,
          accessible_functions: accessibleFunctions,
          accessible_regions: value.role === 'Regional Manager' ? value.accessibleRegions : [],
          accessible_branches: value.role === 'Branch Director' ? value.accessibleBranches : [],
        })
      : await addUser(
          value.name.trim(),
          username,
          value.password,
          value.role,
          isGeneralManagerRole ? [] : value.accessibleTeams,
          hasUnrestrictedTeamAccess,
          accessibleFunctions,
          value.accessibleRegions,
          value.accessibleBranches,
        );
    setBusy(false);
    if (!result.success) {
      setError(result.error || 'Failed to save user');
      return;
    }
    setModalOpen(false);
    setEditingUser(null);
    setSuccess(editingUser ? 'User updated successfully.' : 'User created successfully.');
  };

  const runAction = async (
    action: () => Promise<{ success: boolean; error?: string }>,
    message: string,
  ) => {
    setMenuState(null);
    setError(null);
    setSuccess(null);
    const result = await action();
    if (result.success) setSuccess(message);
    else setError(result.error || 'User action failed');
  };

  const requestDelete = (user: User) => {
    setMenuState(null);
    setError(null);
    setSuccess(null);
    setDeleteError(null);
    setDeleteTarget(user);
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleteBusy(true);
    setDeleteError(null);
    const result = await deleteUser(deleteTarget.id);
    if (result.success) {
      setDeleteTarget(null);
      setSuccess('User deleted successfully.');
    } else {
      setDeleteError(result.error || 'Failed to delete user');
    }
    setDeleteBusy(false);
  };

  const { rows: sortedUsers, sort, toggle } = useTableSort(filteredUsers, USER_SORT_COLUMNS);
  const pagination = usePagination(
    sortedUsers,
    USERS_PER_PAGE,
    `${search}|${roleFilter}|${presenceFilter}|${accountFilter}|${sort?.key ?? ''}|${sort?.direction ?? ''}`,
  );

  const exportUsersCsv = () => {
    const header = ['Name', 'Username', 'Role', 'Access Scope', 'Account Status', 'Presence'];
    const csvRows = [
      header.join(','),
      ...sortedUsers.map((u) =>
        [
          `"${safeUserName(u).replace(/"/g, '""')}"`,
          `"${(u?.username || '').replace(/"/g, '""')}"`,
          `"${(u?.role || '').replace(/"/g, '""')}"`,
          `"${accessScopeText(u).replace(/"/g, '""')}"`,
          (u?.is_active ?? true) ? 'Active' : 'Disabled',
          u?.is_online ? 'Online' : 'Offline',
        ].join(','),
      ),
    ];
    const blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `pms-users-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const renderUserRow = (user: User) => {
    const self = currentUser?.username === user?.username;
    const active = user?.is_active ?? true;
    const online = Boolean(user?.is_online);
    const lastAdmin =
      user?.role === 'Admin' && users.filter((candidate) => candidate?.role === 'Admin').length <= 1;
    return (
      <tr key={user.id} className={`${BODY_ROW_CLASS} ${!active ? 'opacity-60' : ''}`}>
        <td className={BODY_CELL_CLASS}>
          <div className="flex items-center gap-3">
            <span className="relative flex h-8 w-8 items-center justify-center rounded-full bg-blue-500/10 text-xs font-black text-blue-600">
              {userInitials(user)}
              <span
                aria-label={online ? 'Online' : 'Offline'}
                className={`absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-[var(--bg-surface)] ${online ? 'bg-emerald-500' : 'bg-slate-400'}`}
              />
            </span>
            <span className="font-bold text-[var(--text-primary)]">
              {safeUserName(user)}
              {self && <span className="ml-2 text-xs uppercase text-blue-500">You</span>}
            </span>
          </div>
        </td>
        <td className={`${BODY_CELL_CLASS} font-mono text-[var(--text-secondary)]`}>
          @{user?.username || 'unknown'}
        </td>
        <td className={`${BODY_CELL_CLASS} text-[var(--text-secondary)]`}>
          {user?.role || 'Unknown'}
          {user?.legacy_role_needs_reassignment && (
            <span className="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-bold text-amber-800">
              REASSIGN
            </span>
          )}
        </td>
        <td className={`${BODY_CELL_CLASS} max-w-[280px] whitespace-normal`}>{accessScopeText(user)}</td>
        <td className={BODY_CELL_CLASS}>
          <span
            className={`rounded-full px-2 py-1 text-xs font-bold ${active ? 'bg-emerald-500/10 text-emerald-600' : 'bg-slate-500/10 text-slate-500'}`}
          >
            {active ? 'Active' : 'Disabled'}
          </span>
        </td>
        <td className={BODY_CELL_CLASS}>
          <div className="flex flex-col items-start gap-1">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-xs font-bold ${online ? 'bg-emerald-500/10 text-emerald-600' : 'bg-slate-500/10 text-slate-500'}`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${online ? 'bg-emerald-500' : 'bg-slate-400'}`} />
              {online ? 'Online' : 'Offline'}
            </span>
            {!online && (
              <span className="text-xs text-[var(--text-muted)]">{lastSeenText(user?.last_seen_at)}</span>
            )}
          </div>
        </td>
        <td className={`${BODY_CELL_CLASS} relative text-right`}>
          <button
            aria-label={`Actions for ${safeUserName(user)}`}
            aria-expanded={menuState?.userId === user.id}
            onClick={(e) => {
              if (menuState?.userId === user.id) {
                setMenuState(null);
                return;
              }
              setMenuState({ userId: user.id, trigger: e.currentTarget });
            }}
            className="min-h-[44px] !min-w-[44px] rounded-lg p-2 text-[var(--text-muted)] hover:bg-[var(--bg-sunken)] lg:!min-h-[32px] lg:!min-w-[32px]"
          >
            <MoreHorizontal size={17} />
          </button>
          {menuState?.userId === user.id && (
            <UserActionsPopover trigger={menuState.trigger} onClose={closeMenu}>
              <button
                onClick={() => {
                  setEditingUser(user);
                  setError(null);
                  setModalOpen(true);
                  setMenuState(null);
                }}
                className="block w-full px-3 py-2 text-left text-xs hover:bg-[var(--bg-sunken)]"
              >
                Edit
              </button>
              <button
                disabled={self}
                onClick={() =>
                  runAction(
                    () => toggleUserActive(user.id, !active),
                    active ? 'User disabled.' : 'User enabled.',
                  )
                }
                className="block w-full px-3 py-2 text-left text-xs hover:bg-[var(--bg-sunken)] disabled:opacity-40"
              >
                {active ? 'Disable' : 'Enable'}
              </button>
              <button
                disabled={self || lastAdmin || deleteBusy}
                onClick={() => requestDelete(user)}
                className="block w-full px-3 py-2 text-left text-xs text-red-500 hover:bg-red-500/10 disabled:opacity-40"
              >
                Delete
              </button>
            </UserActionsPopover>
          )}
        </td>
      </tr>
    );
  };

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-black text-[var(--text-primary)]">User Management</h2>
          <p className="mt-1 text-xs text-[var(--text-muted)]">
            Manage accounts, roles, branch access and function access.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={exportUsersCsv}
            className="inline-flex items-center gap-1.5 rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3.5 py-2.5 text-xs font-bold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-sunken)] hover:text-[var(--text-primary)]"
          >
            <Download size={14} aria-hidden="true" /> Export CSV
          </button>
          <button
            onClick={() => {
              setEditingUser(null);
              setError(null);
              setModalOpen(true);
            }}
            className="flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-xs font-bold text-white transition-colors hover:bg-blue-700"
          >
            <Plus size={15} /> Add user
          </button>
        </div>
      </header>

      {/* Executive Directory Summary Strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4" aria-label="User directory metrics">
        <div className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-4 py-3 shadow-2xs">
          <span className="block text-[11px] font-semibold tracking-wider text-[var(--text-muted)] uppercase">
            Total Accounts
          </span>
          <span className="mt-1 block text-lg font-black tabular-nums text-[var(--text-primary)]">
            {userStats.total}
          </span>
        </div>
        <div className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-4 py-3 shadow-2xs">
          <span className="flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-[var(--text-muted)] uppercase">
            <span className="size-2 rounded-full bg-emerald-500" aria-hidden="true" />
            Online Now
          </span>
          <span className="mt-1 block text-lg font-black tabular-nums text-emerald-600 dark:text-emerald-400">
            {userStats.onlineCount}
          </span>
        </div>
        <div className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-4 py-3 shadow-2xs">
          <span className="block text-[11px] font-semibold tracking-wider text-[var(--text-muted)] uppercase">
            Active / Disabled
          </span>
          <span className="mt-1 block text-lg font-black tabular-nums text-[var(--text-primary)]">
            {userStats.activeCount}{' '}
            <span className="text-xs font-semibold text-[var(--text-muted)]">
              / {userStats.disabledCount}
            </span>
          </span>
        </div>
        <div className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-4 py-3 shadow-2xs">
          <span className="block text-[11px] font-semibold tracking-wider text-[var(--text-muted)] uppercase">
            Role Reassignments
          </span>
          <span
            className={`mt-1 block text-lg font-black tabular-nums ${userStats.reassignCount > 0 ? 'text-amber-600 dark:text-amber-400' : 'text-[var(--text-primary)]'}`}
          >
            {userStats.reassignCount}
          </span>
        </div>
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-xs font-semibold text-red-600"
        >
          {error}
        </div>
      )}
      {success && (
        <div
          role="status"
          className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-xs font-semibold text-emerald-600"
        >
          {success}
        </div>
      )}
      <AdminTableShell
        tableLabel="Users"
        maxHeightClass="max-h-[560px]"
        minWidthClass="min-w-[860px]"
        toolbar={
          <div className="flex flex-wrap gap-3">
            <label className="flex min-w-[240px] flex-1 items-center gap-2 rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-3 py-2">
              <Search size={14} className="text-[var(--text-muted)]" />
              <input
                aria-label="Search users"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search name or username"
                className="min-w-0 flex-1 bg-transparent text-[13px] text-[var(--text-primary)] outline-none"
              />
            </label>
            <select
              aria-label="Filter by role"
              value={roleFilter}
              onChange={(event) => setRoleFilter(event.target.value)}
              className={FILTER_SELECT}
            >
              <option>All</option>
              {roleFilterOptions.map((role) => (
                <option key={role}>{role}</option>
              ))}
            </select>
            <select
              aria-label="Filter by presence"
              value={presenceFilter}
              onChange={(event) => setPresenceFilter(event.target.value)}
              className={FILTER_SELECT}
            >
              <option>All</option>
              <option>Online</option>
              <option>Offline</option>
            </select>
            <select
              aria-label="Filter by account status"
              value={accountFilter}
              onChange={(event) => setAccountFilter(event.target.value)}
              className={FILTER_SELECT}
            >
              <option value="All">All accounts</option>
              <option value="Active">Active only</option>
              <option value="Disabled">Disabled only</option>
              <option value="Reassign">Needs reassignment</option>
            </select>
          </div>
        }
        footer={
          <TablePagination
            page={pagination.page}
            pageCount={pagination.pageCount}
            from={pagination.from}
            to={pagination.to}
            total={pagination.total}
            onPageChange={pagination.goTo}
            label="Users pages"
          />
        }
      >
        <thead>
          <tr>
            <SortableHeaderCell
              label="User"
              direction={directionFor(sort, 'name')}
              onSort={() => toggle('name')}
            />
            <SortableHeaderCell
              label="Username"
              direction={directionFor(sort, 'username')}
              onSort={() => toggle('username')}
            />
            <SortableHeaderCell
              label="Role"
              direction={directionFor(sort, 'role')}
              onSort={() => toggle('role')}
            />
            <th scope="col" className={HEAD_CELL_CLASS}>
              Access scope
            </th>
            <SortableHeaderCell
              label="Account"
              direction={directionFor(sort, 'account')}
              onSort={() => toggle('account')}
            />
            <SortableHeaderCell
              label="Presence"
              direction={directionFor(sort, 'presence')}
              onSort={() => toggle('presence')}
            />
            <th scope="col" className={`${HEAD_CELL_CLASS} text-right`}>
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--border-light)]">
          {pagination.rows.map((user) => renderUserRow(user))}
          {!pagination.rows.length && (
            <TableEmptyRow colSpan={7} icon={Users} message="No users match the current filters." />
          )}
        </tbody>
      </AdminTableShell>
      {modalOpen && (
        <UserFormModal
          open
          user={editingUser}
          teams={teams}
          busy={busy}
          error={error}
          onClose={() => {
            setModalOpen(false);
            setEditingUser(null);
            setError(null);
          }}
          onSubmit={submit}
        />
      )}
      {deleteTarget && (
        <div
          role="presentation"
          className="fixed inset-0 z-[10000] flex items-center justify-center bg-slate-950/55 p-4 backdrop-blur-sm"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !deleteBusy) setDeleteTarget(null);
          }}
        >
          <div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="delete-user-title"
            aria-describedby="delete-user-description"
            className="w-full max-w-md rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-6 shadow-2xl"
          >
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-red-500/10 text-red-600">
                !
              </div>
              <div>
                <h3 id="delete-user-title" className="text-base font-black text-[var(--text-primary)]">
                  Delete user?
                </h3>
                <p id="delete-user-description" className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
                  This permanently removes <strong>{safeUserName(deleteTarget)}</strong> and revokes their
                  active sessions.
                </p>
              </div>
            </div>
            {deleteError && (
              <div
                role="alert"
                className="mt-4 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs font-semibold text-red-600"
              >
                {deleteError}
              </div>
            )}
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                disabled={deleteBusy}
                onClick={() => setDeleteTarget(null)}
                className="rounded-xl border border-[var(--border-light)] px-4 py-2.5 text-xs font-bold text-[var(--text-secondary)] disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={deleteBusy}
                onClick={() => void confirmDelete()}
                className="rounded-xl bg-red-600 px-4 py-2.5 text-xs font-bold text-white disabled:opacity-50"
              >
                {deleteBusy ? 'Deleting…' : 'Delete user'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
