import { useState } from 'react';
import { X } from 'lucide-react';
import type { User } from '../../types';
import type { TeamConfigItem } from './types';
import { USER_BRANCH_OPTIONS, USER_REGION_OPTIONS, USER_ROLE_OPTIONS, readHasUnrestrictedTeamAccess } from '../../lib/access';
import { EXECUTIVE_FUNCTIONS, isPreApprovalsSubTeam } from '../../features/executive/functions';

export interface UserFormValue {
  name: string;
  username: string;
  password: string;
  role: User['role'];
  accessibleTeams: string[];
  accessibleFunctions: string[];
  accessibleRegions: string[];
  accessibleBranches: string[];
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

const emptyForm: UserFormValue = { name: '', username: '', password: '', role: 'Employee', accessibleTeams: [], accessibleFunctions: [], accessibleRegions: [], accessibleBranches: [], isGeneralManager: false };

export function UserFormModal({ open, user, teams, busy, error, onClose, onSubmit }: UserFormModalProps) {
  const [form, setForm] = useState<UserFormValue>(() => user ? {
      name: user.name || '', username: user.username || '', password: '', role: user.role || 'Employee',
      accessibleTeams: Array.isArray(user.accessible_teams) ? user.accessible_teams : [],
      accessibleFunctions: Array.isArray(user.accessible_functions) ? user.accessible_functions : [],
      accessibleRegions: Array.isArray(user.accessible_regions) ? user.accessible_regions : [],
      accessibleBranches: Array.isArray(user.accessible_branches) ? user.accessible_branches : [],
      isGeneralManager: readHasUnrestrictedTeamAccess(user),
    } : emptyForm);

  if (!open) return null;
  const isLegacyRole = !USER_ROLE_OPTIONS.includes(form.role);
  const isReassigningLegacyRole = Boolean(user?.legacy_role_needs_reassignment || isLegacyRole);
  const approvalsTeams = [...new Set(teams.filter((team) => isPreApprovalsSubTeam(team.name)).map((team) => team.name))];
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="user-form-title" className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 p-4 backdrop-blur-sm" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <form onSubmit={(event) => { event.preventDefault(); void onSubmit(form); }} className="max-h-[90vh] w-full max-w-xl overflow-auto rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-2xl">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-[var(--border-light)] bg-[var(--bg-surface)] px-4 py-3 sm:px-6 sm:py-4"><div><h3 id="user-form-title" className="text-base font-black text-[var(--text-primary)]">{user ? 'Edit user' : 'Add user'}</h3><p className="text-[10px] text-[var(--text-muted)]">Account, role and access scope</p></div><button type="button" aria-label="Close user form" onClick={onClose} className="rounded-lg p-2 text-[var(--text-muted)] hover:bg-[var(--bg-sunken)]"><X size={18} /></button></div>
        <div className="space-y-4 p-4 sm:p-6">
          {error && <div role="alert" className="rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs font-semibold text-red-600">{error}</div>}
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="text-xs font-bold text-[var(--text-secondary)]">Full name<input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} className="mt-1.5 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-3 py-2.5 text-xs text-[var(--text-primary)] outline-none focus:border-blue-500" /></label>
            <label className="text-xs font-bold text-[var(--text-secondary)]">Username<input required value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} className="mt-1.5 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-3 py-2.5 text-xs text-[var(--text-primary)] outline-none focus:border-blue-500" /></label>
            <label className="text-xs font-bold text-[var(--text-secondary)]">{user ? 'Password' : 'Temporary password'} {user && <span className="font-normal text-[var(--text-muted)]">(leave blank to keep)</span>}<input required={!user} type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} className="mt-1.5 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-3 py-2.5 text-xs text-[var(--text-primary)] outline-none focus:border-blue-500" />{!user && <span className="mt-1.5 block font-normal text-[var(--text-muted)]">The user must set a new password on first sign-in.</span>}</label>
            <label className="text-xs font-bold text-[var(--text-secondary)]">Role<select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value as User['role'] })} className="mt-1.5 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-3 py-2.5 text-xs text-[var(--text-primary)] outline-none">{isLegacyRole && <option value={form.role} disabled>{form.role} — legacy; select a replacement</option>}{USER_ROLE_OPTIONS.map((role) => <option key={role} value={role}>{role}</option>)}</select></label>
          </div>
          {isReassigningLegacyRole && <p role="status" className="rounded-2xl border border-amber-300 bg-amber-50 p-4 text-xs font-semibold text-amber-800">This account has a legacy role. Its existing access remains temporarily; choose a current role to complete reassignment.</p>}
          {form.role === 'Performance Team' && <p className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-sunken)] p-4 text-xs font-semibold text-[var(--text-secondary)]">Broad operational access across the system. Admin Settings, user administration, and security configuration remain unavailable.</p>}
          {form.role === 'Manager' && approvalsTeams.length > 0 && <fieldset className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-sunken)] p-4"><legend className="px-1 text-xs font-black text-[var(--text-primary)]">RCM / Pre-Approvals</legend><label className="flex items-center gap-2 text-xs font-bold text-[var(--text-secondary)]"><input type="checkbox" disabled={form.isGeneralManager} checked={form.isGeneralManager || approvalsTeams.every((name) => form.accessibleTeams.includes(name))} onChange={(event) => setForm({ ...form, accessibleTeams: event.target.checked ? [...new Set([...form.accessibleTeams, ...approvalsTeams])] : form.accessibleTeams.filter((name) => !approvalsTeams.includes(name)) })} />All Pre-Approvals sub-teams</label><p className="mt-2 text-[10px] text-[var(--text-muted)]">This explicitly selects the available Pre-Approvals sub-teams only, not Coding, Submission or other RCM teams. Use the individual team choices below for narrower access.</p></fieldset>}
          {(form.role === 'Function Director' || form.role === 'Function Viewer') && <p className="text-xs text-[var(--text-muted)]">RCM includes Pre-Approvals and its sub-teams. {form.accessibleFunctions.includes('Pre-Approvals') && 'The existing legacy Pre-Approvals grant is retained with UAE-only access; selecting RCM explicitly grants the whole function.'}</p>}
          {form.role === 'Manager' && <fieldset className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-sunken)] p-4"><legend className="px-1 text-xs font-black text-[var(--text-primary)]">Branch / team access</legend><label className="flex items-center gap-2 text-xs font-bold text-[var(--text-secondary)]"><input type="checkbox" checked={form.isGeneralManager} onChange={(event) => setForm({ ...form, isGeneralManager: event.target.checked, accessibleTeams: event.target.checked ? [] : form.accessibleTeams })} /> All branches</label>{!form.isGeneralManager && <div className="mt-3 grid max-h-40 gap-2 overflow-auto sm:grid-cols-2">{teams.map((team) => <label key={team.name} className="flex items-center gap-2 rounded-lg bg-[var(--bg-surface)] px-3 py-2 text-xs text-[var(--text-secondary)]"><input type="checkbox" checked={form.accessibleTeams.includes(team.name)} onChange={(event) => setForm({ ...form, accessibleTeams: event.target.checked ? [...form.accessibleTeams, team.name] : form.accessibleTeams.filter((name) => name !== team.name) })} />{team.name}</label>)}</div>}<p className="mt-2 text-[10px] text-[var(--text-muted)]">Choose the branches (teams) this Manager can open.</p></fieldset>}
          {form.role === 'Regional Manager' && <fieldset className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-sunken)] p-4"><legend className="px-1 text-xs font-black text-[var(--text-primary)]">Region access</legend><div className="grid gap-2 sm:grid-cols-3">{USER_REGION_OPTIONS.map((region) => <label key={region} className="flex items-center gap-2 rounded-lg bg-[var(--bg-surface)] px-3 py-2 text-xs text-[var(--text-secondary)]"><input type="checkbox" checked={form.accessibleRegions.includes(region)} onChange={(event) => setForm({ ...form, accessibleRegions: event.target.checked ? [...form.accessibleRegions, region] : form.accessibleRegions.filter((value) => value !== region) })} />{region}</label>)}</div><p className="mt-2 text-[10px] text-[var(--text-muted)]">Read access is restricted to the selected regions.</p></fieldset>}
          {form.role === 'Branch Director' && <fieldset className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-sunken)] p-4"><legend className="px-1 text-xs font-black text-[var(--text-primary)]">Branch access</legend><div className="grid gap-2 sm:grid-cols-2">{USER_BRANCH_OPTIONS.map((branch) => <label key={branch.key} className="flex items-center gap-2 rounded-lg bg-[var(--bg-surface)] px-3 py-2 text-xs text-[var(--text-secondary)]"><input type="checkbox" checked={form.accessibleBranches.includes(branch.key)} onChange={(event) => setForm({ ...form, accessibleBranches: event.target.checked ? [...form.accessibleBranches, branch.key] : form.accessibleBranches.filter((value) => value !== branch.key) })} />{branch.label}</label>)}</div><p className="mt-2 text-[10px] text-[var(--text-muted)]">Only records with a unique explicit branch source are visible. Geo totals do not grant access.</p></fieldset>}
          {(form.role === 'Function Director' || form.role === 'Function Viewer') && <fieldset className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-sunken)] p-4"><legend className="px-1 text-xs font-black text-[var(--text-primary)]">Function access</legend><div className="grid gap-2 sm:grid-cols-2">{EXECUTIVE_FUNCTIONS.map((functionName) => <label key={functionName} className="flex items-center gap-2 rounded-lg bg-[var(--bg-surface)] px-3 py-2 text-xs text-[var(--text-secondary)]"><input type="checkbox" checked={form.accessibleFunctions.includes(functionName)} onChange={(event) => setForm({ ...form, accessibleFunctions: event.target.checked ? [...form.accessibleFunctions, functionName] : form.accessibleFunctions.filter((name) => name !== functionName) })} />{functionName}</label>)}</div><p className="mt-2 text-[10px] text-[var(--text-muted)]">Function Directors can read their assigned functions across branches.</p></fieldset>}
          {form.role === 'Employee' && <p className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-sunken)] p-4 text-xs font-semibold text-[var(--text-secondary)]">Employee accounts are limited to the matching employee’s own profile and performance records.</p>}
        </div>
        <div className="sticky bottom-0 flex justify-end gap-2 border-t border-[var(--border-light)] bg-[var(--bg-surface)] px-4 py-3 sm:px-6 sm:py-4"><button type="button" onClick={onClose} disabled={busy} className="rounded-xl border border-[var(--border-light)] px-4 py-2.5 text-xs font-bold text-[var(--text-secondary)]">Cancel</button><button type="submit" disabled={busy || (isReassigningLegacyRole && form.role === user?.role)} className="rounded-xl bg-blue-600 px-5 py-2.5 text-xs font-bold text-white disabled:opacity-50">{busy ? 'Saving…' : user ? 'Save changes' : 'Create user'}</button></div>
      </form>
    </div>
  );
}
