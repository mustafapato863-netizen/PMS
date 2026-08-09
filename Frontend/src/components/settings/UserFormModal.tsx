import { useState } from 'react';
import { X } from 'lucide-react';
import type { User } from '../../types';
import type { TeamConfigItem } from './types';

export interface UserFormValue {
  name: string;
  username: string;
  password: string;
  role: User['role'];
  accessibleTeams: string[];
  isGeneralManager: boolean;
}

interface UserFormModalProps {
  open: boolean;
  user?: User | null;
  teams: TeamConfigItem[];
  busy?: boolean;
  error?: string | null;
  onClose: () => void;
  onSubmit: (value: UserFormValue) => Promise<void>;
}

const emptyForm: UserFormValue = { name: '', username: '', password: '', role: 'Viewer', accessibleTeams: [], isGeneralManager: false };

export function UserFormModal({ open, user, teams, busy, error, onClose, onSubmit }: UserFormModalProps) {
  const [form, setForm] = useState<UserFormValue>(() => user ? {
      name: user.name || '', username: user.username || '', password: '', role: user.role || 'Viewer',
      accessibleTeams: Array.isArray(user.accessible_teams) ? user.accessible_teams : [],
      isGeneralManager: Boolean(user.is_general_manager),
    } : emptyForm);

  if (!open) return null;
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="user-form-title" className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 p-4 backdrop-blur-sm" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <form onSubmit={(event) => { event.preventDefault(); void onSubmit(form); }} className="max-h-[90vh] w-full max-w-xl overflow-auto rounded-3xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-2xl">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-[var(--border-light)] bg-[var(--bg-surface)] px-6 py-4"><div><h3 id="user-form-title" className="text-base font-black text-[var(--text-primary)]">{user ? 'Edit user' : 'Add user'}</h3><p className="text-[10px] text-[var(--text-muted)]">Account, role and team access</p></div><button type="button" aria-label="Close user form" onClick={onClose} className="rounded-lg p-2 text-[var(--text-muted)] hover:bg-[var(--bg-sunken)]"><X size={18} /></button></div>
        <div className="space-y-4 p-6">
          {error && <div role="alert" className="rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs font-semibold text-red-600">{error}</div>}
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="text-xs font-bold text-[var(--text-secondary)]">Full name<input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} className="mt-1.5 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-3 py-2.5 text-xs text-[var(--text-primary)] outline-none focus:border-blue-500" /></label>
            <label className="text-xs font-bold text-[var(--text-secondary)]">Username<input required value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} className="mt-1.5 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-3 py-2.5 text-xs text-[var(--text-primary)] outline-none focus:border-blue-500" /></label>
            <label className="text-xs font-bold text-[var(--text-secondary)]">Password {user && <span className="font-normal text-[var(--text-muted)]">(leave blank to keep)</span>}<input required={!user} type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} className="mt-1.5 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-3 py-2.5 text-xs text-[var(--text-primary)] outline-none focus:border-blue-500" /></label>
            <label className="text-xs font-bold text-[var(--text-secondary)]">Role<select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value as User['role'] })} className="mt-1.5 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-3 py-2.5 text-xs text-[var(--text-primary)] outline-none">{['Admin', 'Manager', 'Executive', 'Viewer', 'Agent'].map((role) => <option key={role}>{role}</option>)}</select></label>
          </div>
          {form.role === 'Manager' && <div className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-sunken)] p-4"><label className="flex items-center gap-2 text-xs font-bold text-[var(--text-secondary)]"><input type="checkbox" checked={form.isGeneralManager} onChange={(event) => setForm({ ...form, isGeneralManager: event.target.checked, accessibleTeams: event.target.checked ? [] : form.accessibleTeams })} /> General manager (all teams)</label>{!form.isGeneralManager && <div className="mt-3 grid max-h-40 gap-2 overflow-auto sm:grid-cols-2">{teams.map((team) => <label key={team.name} className="flex items-center gap-2 rounded-lg bg-[var(--bg-surface)] px-3 py-2 text-xs text-[var(--text-secondary)]"><input type="checkbox" checked={form.accessibleTeams.includes(team.name)} onChange={(event) => setForm({ ...form, accessibleTeams: event.target.checked ? [...form.accessibleTeams, team.name] : form.accessibleTeams.filter((name) => name !== team.name) })} />{team.name}</label>)}</div>}</div>}
        </div>
        <div className="sticky bottom-0 flex justify-end gap-2 border-t border-[var(--border-light)] bg-[var(--bg-surface)] px-6 py-4"><button type="button" onClick={onClose} disabled={busy} className="rounded-xl border border-[var(--border-light)] px-4 py-2.5 text-xs font-bold text-[var(--text-secondary)]">Cancel</button><button type="submit" disabled={busy} className="rounded-xl bg-blue-600 px-5 py-2.5 text-xs font-bold text-white disabled:opacity-50">{busy ? 'Saving…' : user ? 'Save changes' : 'Create user'}</button></div>
      </form>
    </div>
  );
}
