import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { formatDistanceToNow } from 'date-fns';
import { MoreHorizontal, Plus, Search, Users } from 'lucide-react';
import { API_BASE } from '../../config';
import { useAuth } from '../../context/auth';
import { useUserRole } from '../../context/RoleContext';
import type { User } from '../../types';
import type { TeamConfigItem } from './types';
import { UserFormModal, type UserFormValue } from './UserFormModal';
import { safeUserName, userInitials } from './settingsUtils';

function lastSeenText(value?: string | null) {
  if (!value) return 'Never seen';
  const lastSeen = new Date(value);
  if (Number.isNaN(lastSeen.getTime())) return 'Never seen';
  return `Last seen ${formatDistanceToNow(lastSeen, { addSuffix: true })}`;
}

export function UserManagementPanel() {
  const { users, currentUser, addUser, updateUser, deleteUser, toggleUserActive, refreshUsers } = useAuth();
  const { fetchWithRole } = useUserRole();
  const [teams, setTeams] = useState<TeamConfigItem[]>([]);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('All');
  const [presenceFilter, setPresenceFilter] = useState('All');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [menuState, setMenuState] = useState<{ userId: string; top: number; right: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const load = useCallback(async () => {
    await refreshUsers();
    const response = await fetchWithRole(`${API_BASE}/api/config/teams`);
    if (!response.ok) return;
    const result = await response.json();
    setTeams((Array.isArray(result?.data) ? result.data : []).map((item: unknown) => {
      const record = typeof item === 'object' && item !== null ? item as Record<string, unknown> : {};
      return { name: String(record.name ?? record.db_name ?? item ?? '') };
    }).filter((item: TeamConfigItem) => item.name));
  }, [fetchWithRole, refreshUsers]);

  useEffect(() => { void Promise.resolve().then(load).catch((caught) => setError(caught instanceof Error ? caught.message : 'Failed to load users')); }, [load]);

  // Close menu on scroll or resize
  useEffect(() => {
    if (!menuState) return;
    const handleClose = () => setMenuState(null);
    window.addEventListener('scroll', handleClose, true);
    window.addEventListener('resize', handleClose);
    return () => {
      window.removeEventListener('scroll', handleClose, true);
      window.removeEventListener('resize', handleClose);
    };
  }, [menuState]);

  const filteredUsers = useMemo(() => {
    const term = search.trim().toLowerCase();
    return (Array.isArray(users) ? users : []).filter((user) => {
      const name = typeof user?.name === 'string' ? user.name : '';
      const username = typeof user?.username === 'string' ? user.username : '';
      const matchesSearch = !term || name.toLowerCase().includes(term) || username.toLowerCase().includes(term);
      const matchesRole = roleFilter === 'All' || user?.role === roleFilter;
      const matchesPresence = presenceFilter === 'All'
        || (presenceFilter === 'Online' ? user?.is_online : !user?.is_online);
      return matchesSearch && matchesRole && matchesPresence;
    });
  }, [users, search, roleFilter, presenceFilter]);

  const submit = async (value: UserFormValue) => {
    setBusy(true); setError(null); setSuccess(null);
    const username = value.username.trim().toLowerCase();
    const result = editingUser
      ? await updateUser(editingUser.id, { name: value.name.trim(), username, password: value.password.trim() || undefined, role: value.role, is_active: editingUser.is_active ?? true, accessible_teams: value.role === 'Manager' ? value.accessibleTeams : [], is_general_manager: value.role === 'Manager' && value.isGeneralManager })
      : await addUser(value.name.trim(), username, value.password, value.role, value.accessibleTeams, value.isGeneralManager);
    setBusy(false);
    if (!result.success) { setError(result.error || 'Failed to save user'); return; }
    setModalOpen(false); setEditingUser(null); setSuccess(editingUser ? 'User updated successfully.' : 'User created successfully.');
  };

  const runAction = async (action: () => Promise<{ success: boolean; error?: string }>, message: string) => {
    setMenuState(null); setError(null); setSuccess(null);
    const result = await action();
    if (result.success) setSuccess(message);
    else setError(result.error || 'User action failed');
  };

  return <div className="space-y-6">
    <header className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-xl font-black text-[var(--text-primary)]">User Management</h2><p className="mt-1 text-xs text-[var(--text-muted)]">Manage accounts, roles and team access.</p></div><button onClick={() => { setEditingUser(null); setError(null); setModalOpen(true); }} className="flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-xs font-bold text-white"><Plus size={15} /> Add user</button></header>
    {error && <div role="alert" className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-xs font-semibold text-red-600">{error}</div>}{success && <div role="status" className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-xs font-semibold text-emerald-600">{success}</div>}
    <section className="glass-panel overflow-hidden rounded-3xl border border-[var(--border-light)] shadow-sm">
      <div className="flex flex-wrap gap-3 border-b border-[var(--border-light)] p-4"><label className="flex min-w-[240px] flex-1 items-center gap-2 rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-3 py-2"><Search size={14} className="text-[var(--text-muted)]" /><input aria-label="Search users" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name or username" className="min-w-0 flex-1 bg-transparent text-xs text-[var(--text-primary)] outline-none" /></label><select aria-label="Filter by role" value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)} className="rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-3 py-2 text-xs font-semibold text-[var(--text-secondary)]"><option>All</option>{['Admin', 'Manager', 'Executive', 'Viewer', 'Agent'].map((role) => <option key={role}>{role}</option>)}</select><select aria-label="Filter by presence" value={presenceFilter} onChange={(event) => setPresenceFilter(event.target.value)} className="rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-3 py-2 text-xs font-semibold text-[var(--text-secondary)]"><option>All</option><option>Online</option><option>Offline</option></select></div>
      <div className="max-h-[560px] overflow-auto"><table className="w-full min-w-[880px] text-left text-xs"><thead className="sticky top-0 z-10 bg-[var(--bg-sunken)] text-[10px] uppercase tracking-wider text-[var(--text-muted)]"><tr><th className="px-5 py-3">User</th><th className="px-5 py-3">Username</th><th className="px-5 py-3">Role</th><th className="px-5 py-3">Account</th><th className="px-5 py-3">Presence</th><th className="px-5 py-3 text-right">Actions</th></tr></thead><tbody className="divide-y divide-[var(--border-light)]">{filteredUsers.map((user) => { const self = currentUser?.username === user?.username; const active = user?.is_active ?? true; const online = Boolean(user?.is_online); const lastAdmin = user?.role === 'Admin' && users.filter((candidate) => candidate?.role === 'Admin').length <= 1; return <tr key={user.id} className={!active ? 'opacity-60' : ''}><td className="px-5 py-3"><div className="flex items-center gap-3"><span className="relative flex h-8 w-8 items-center justify-center rounded-full bg-blue-500/10 text-[10px] font-black text-blue-600">{userInitials(user)}<span aria-label={online ? 'Online' : 'Offline'} className={`absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-[var(--bg-surface)] ${online ? 'bg-emerald-500' : 'bg-slate-400'}`} /></span><span className="font-bold text-[var(--text-primary)]">{safeUserName(user)}{self && <span className="ml-2 text-[9px] uppercase text-blue-500">You</span>}</span></div></td><td className="px-5 py-3 font-mono text-[var(--text-secondary)]">@{user?.username || 'unknown'}</td><td className="px-5 py-3 text-[var(--text-secondary)]">{user?.role || 'Unknown'}</td><td className="px-5 py-3"><span className={`rounded-full px-2 py-1 text-[10px] font-bold ${active ? 'bg-emerald-500/10 text-emerald-600' : 'bg-slate-500/10 text-slate-500'}`}>{active ? 'Active' : 'Disabled'}</span></td><td className="px-5 py-3"><div className="flex flex-col items-start gap-1"><span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-[10px] font-bold ${online ? 'bg-emerald-500/10 text-emerald-600' : 'bg-slate-500/10 text-slate-500'}`}><span className={`h-1.5 w-1.5 rounded-full ${online ? 'bg-emerald-500' : 'bg-slate-400'}`} />{online ? 'Online' : 'Offline'}</span>{!online && <span className="text-[10px] text-[var(--text-muted)]">{lastSeenText(user?.last_seen_at)}</span>}</div></td><td className="relative px-5 py-3 text-right">
        <button aria-label={`Actions for ${safeUserName(user)}`} onClick={(e) => {
          if (menuState?.userId === user.id) { setMenuState(null); return; }
          const rect = e.currentTarget.getBoundingClientRect();
          setMenuState({ userId: user.id, top: rect.bottom + 4, right: window.innerWidth - rect.right });
        }} className="rounded-lg p-2 text-[var(--text-muted)] hover:bg-[var(--bg-sunken)]"><MoreHorizontal size={17} /></button>
        {menuState?.userId === user.id && createPortal(<div style={{ top: menuState.top, right: menuState.right }} className="fixed z-[9999] w-36 overflow-hidden rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] py-1 text-left shadow-xl"><button onClick={() => { setEditingUser(user); setError(null); setModalOpen(true); setMenuState(null); }} className="block w-full px-3 py-2 text-left hover:bg-[var(--bg-sunken)] text-xs">Edit</button><button disabled={self} onClick={() => runAction(() => toggleUserActive(user.id, !active), active ? 'User disabled.' : 'User enabled.')} className="block w-full px-3 py-2 text-left hover:bg-[var(--bg-sunken)] disabled:opacity-40 text-xs">{active ? 'Disable' : 'Enable'}</button><button disabled={self || lastAdmin} onClick={() => { if (window.confirm(`Delete ${safeUserName(user)}?`)) void runAction(() => deleteUser(user.id), 'User deleted.'); }} className="block w-full px-3 py-2 text-left text-red-500 hover:bg-red-500/10 disabled:opacity-40 text-xs">Delete</button></div>, document.body)}
        </td></tr>; })}{!filteredUsers.length && <tr><td colSpan={6} className="px-5 py-12 text-center text-[var(--text-muted)]"><Users size={25} className="mx-auto mb-2" />No users match the current filters.</td></tr>}</tbody></table></div>
    </section>
    {modalOpen && <UserFormModal open user={editingUser} teams={teams} busy={busy} error={error} onClose={() => { setModalOpen(false); setEditingUser(null); setError(null); }} onSubmit={submit} />}
  </div>;
}
