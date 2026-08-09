import { useState, type FormEvent } from 'react';
import { KeyRound, UserRound, X } from 'lucide-react';

import type { User } from '../../types';

type ActionResult = { success: boolean; error?: string };

interface ProfileSettingsModalProps {
  user: User;
  onClose: () => void;
  onUpdateProfile: (fullName: string) => Promise<ActionResult>;
  onChangePassword: (currentPassword: string, newPassword: string) => Promise<ActionResult>;
}

export function ProfileSettingsModal({
  user,
  onClose,
  onUpdateProfile,
  onChangePassword,
}: ProfileSettingsModalProps) {
  const [fullName, setFullName] = useState(user.name || '');
  const [nameBusy, setNameBusy] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);
  const [nameSuccess, setNameSuccess] = useState<string | null>(null);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState<string | null>(null);

  const submitName = async (event: FormEvent) => {
    event.preventDefault();
    setNameError(null);
    setNameSuccess(null);
    const normalized = fullName.trim();
    if (!normalized) {
      setNameError('Full name is required.');
      return;
    }
    setNameBusy(true);
    const result = await onUpdateProfile(normalized);
    setNameBusy(false);
    if (!result.success) {
      setNameError(result.error || 'Failed to update profile.');
      return;
    }
    setFullName(normalized);
    setNameSuccess('Full name updated successfully.');
  };

  const submitPassword = async (event: FormEvent) => {
    event.preventDefault();
    setPasswordError(null);
    setPasswordSuccess(null);
    if (newPassword !== confirmPassword) {
      setPasswordError('New passwords do not match.');
      return;
    }
    setPasswordBusy(true);
    const result = await onChangePassword(currentPassword, newPassword);
    setPasswordBusy(false);
    if (!result.success) {
      setPasswordError(result.error || 'Failed to change password.');
      return;
    }
    setCurrentPassword('');
    setNewPassword('');
    setConfirmPassword('');
    setPasswordSuccess('Password changed successfully.');
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="profile-settings-title"
      className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/55 p-4 backdrop-blur-sm"
      onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}
    >
      <div className="max-h-[92vh] w-full max-w-2xl overflow-auto rounded-3xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-2xl">
        <header className="sticky top-0 z-10 flex items-center justify-between border-b border-[var(--border-light)] bg-[var(--bg-surface)] px-6 py-4">
          <div>
            <h2 id="profile-settings-title" className="text-base font-black text-[var(--text-primary)]">My profile</h2>
            <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">Manage your display name and account password</p>
          </div>
          <button type="button" aria-label="Close profile settings" onClick={onClose} className="rounded-xl p-2 text-[var(--text-muted)] hover:bg-[var(--bg-sunken)]">
            <X size={18} />
          </button>
        </header>

        <div className="grid gap-5 p-6">
          <form onSubmit={submitName} className="rounded-2xl border border-[var(--border-light)] p-5">
            <div className="mb-4 flex items-center gap-3">
              <span className="rounded-xl bg-blue-500/10 p-2 text-blue-600"><UserRound size={18} /></span>
              <div><h3 className="text-sm font-black text-[var(--text-primary)]">Profile information</h3><p className="text-[10px] text-[var(--text-muted)]">Your username remains unchanged.</p></div>
            </div>
            {nameError && <div role="alert" className="mb-3 rounded-xl bg-red-500/10 px-3 py-2 text-xs font-semibold text-red-600">{nameError}</div>}
            {nameSuccess && <div role="status" className="mb-3 rounded-xl bg-emerald-500/10 px-3 py-2 text-xs font-semibold text-emerald-600">{nameSuccess}</div>}
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="text-xs font-bold text-[var(--text-secondary)]">Full name<input aria-label="Full name" required maxLength={255} value={fullName} onChange={(event) => setFullName(event.target.value)} className="mt-1.5 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-3 py-2.5 text-xs text-[var(--text-primary)] outline-none focus:border-blue-500" /></label>
              <label className="text-xs font-bold text-[var(--text-secondary)]">Username<input aria-label="Username" readOnly value={user.username} className="mt-1.5 w-full cursor-not-allowed rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-3 py-2.5 font-mono text-xs text-[var(--text-muted)] outline-none" /></label>
            </div>
            <div className="mt-4 flex justify-end"><button type="submit" disabled={nameBusy} className="rounded-xl bg-blue-600 px-4 py-2.5 text-xs font-bold text-white disabled:opacity-50">{nameBusy ? 'Saving…' : 'Save name'}</button></div>
          </form>

          <form onSubmit={submitPassword} className="rounded-2xl border border-[var(--border-light)] p-5">
            <div className="mb-4 flex items-center gap-3">
              <span className="rounded-xl bg-violet-500/10 p-2 text-violet-600"><KeyRound size={18} /></span>
              <div><h3 className="text-sm font-black text-[var(--text-primary)]">Change password</h3><p className="text-[10px] text-[var(--text-muted)]">Use 12+ characters with uppercase, lowercase, number and symbol.</p></div>
            </div>
            {passwordError && <div role="alert" className="mb-3 rounded-xl bg-red-500/10 px-3 py-2 text-xs font-semibold text-red-600">{passwordError}</div>}
            {passwordSuccess && <div role="status" className="mb-3 rounded-xl bg-emerald-500/10 px-3 py-2 text-xs font-semibold text-emerald-600">{passwordSuccess}</div>}
            <div className="grid gap-4">
              <label className="text-xs font-bold text-[var(--text-secondary)]">Current password<input aria-label="Current password" required type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} className="mt-1.5 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-3 py-2.5 text-xs text-[var(--text-primary)] outline-none focus:border-violet-500" /></label>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="text-xs font-bold text-[var(--text-secondary)]">New password<input aria-label="New password" required minLength={12} maxLength={72} type="password" autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} className="mt-1.5 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-3 py-2.5 text-xs text-[var(--text-primary)] outline-none focus:border-violet-500" /></label>
                <label className="text-xs font-bold text-[var(--text-secondary)]">Confirm new password<input aria-label="Confirm new password" required minLength={12} maxLength={72} type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} className="mt-1.5 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-3 py-2.5 text-xs text-[var(--text-primary)] outline-none focus:border-violet-500" /></label>
              </div>
            </div>
            <div className="mt-4 flex justify-end"><button type="submit" disabled={passwordBusy} className="rounded-xl bg-violet-600 px-4 py-2.5 text-xs font-bold text-white disabled:opacity-50">{passwordBusy ? 'Changing…' : 'Change password'}</button></div>
          </form>
        </div>
      </div>
    </div>
  );
}
