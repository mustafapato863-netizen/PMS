import { useState, type FormEvent } from 'react';
import { KeyRound, LogOut, ShieldCheck } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/auth';
import { useToast } from '../hooks/useToast';

export default function FirstLoginPasswordChange() {
  const { currentUser, changePassword, logout } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setError(null);
    if (newPassword !== confirmation) {
      setError('New passwords do not match.');
      return;
    }
    if (newPassword === currentPassword) {
      setError('Choose a password different from your temporary password.');
      return;
    }
    setBusy(true);
    try {
      const result = await changePassword(currentPassword, newPassword);
      if (!result.success) {
        setError(result.error || 'Unable to change your password. Please try again.');
        return;
      }
      setCurrentPassword('');
      setNewPassword('');
      setConfirmation('');
      toast.success('Password updated. Sign in with your new password.', 8000);
      logout();
      navigate('/login', { replace: true });
    } catch {
      setError('Unable to change your password. Please try again.');
    } finally {
      setBusy(false);
    }
  };
  const inputClass = 'mt-2 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-4 py-3 text-sm text-[var(--text-primary)] focus-visible:outline-2 focus-visible:outline-[var(--sgh-cyan-primary)]';
  return <main className="flex min-h-screen items-center justify-center bg-[var(--bg-base)] p-4">
    <section aria-labelledby="first-password-title" className="w-full max-w-lg rounded-3xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-6 shadow-xl sm:p-8">
      <span aria-hidden="true" className="mb-5 inline-flex rounded-2xl bg-cyan-500/10 p-3 text-[var(--sgh-cyan-primary)]"><ShieldCheck size={28} /></span>
      <h1 id="first-password-title" className="text-2xl font-extrabold text-[var(--text-primary)]">Secure your account</h1>
      <p className="mt-2 text-sm text-[var(--text-secondary)]">Welcome, {currentUser?.name || currentUser?.username}. Change the temporary password supplied by your administrator before entering SGH Hub.</p>
      <p id="password-policy" className="mt-4 text-xs text-[var(--text-muted)]">Use 12–72 characters with uppercase, lowercase, a number and a symbol. You’ll sign in again with your new password.</p>
      <form onSubmit={submit} className="mt-6 space-y-4">
        {error && <p role="alert" className="rounded-xl bg-red-500/10 p-3 text-sm text-red-600">{error}</p>}
        <label className="block text-sm font-semibold text-[var(--text-secondary)]">Temporary password<input required disabled={busy} type="password" autoComplete="current-password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} className={inputClass} /></label>
        <label className="block text-sm font-semibold text-[var(--text-secondary)]">New password<input required disabled={busy} minLength={12} maxLength={72} aria-describedby="password-policy" type="password" autoComplete="new-password" value={newPassword} onChange={e => setNewPassword(e.target.value)} className={inputClass} /></label>
        <label className="block text-sm font-semibold text-[var(--text-secondary)]">Confirm new password<input required disabled={busy} minLength={12} maxLength={72} type="password" autoComplete="new-password" value={confirmation} onChange={e => setConfirmation(e.target.value)} className={inputClass} /></label>
        <button disabled={busy} type="submit" className="flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-[var(--sgh-cyan-primary)] px-4 py-3 text-sm font-bold text-white disabled:opacity-60"><KeyRound size={17} aria-hidden="true" />{busy ? 'Updating password…' : 'Set password and sign in'}</button>
        <button disabled={busy} type="button" onClick={logout} className="flex min-h-11 w-full items-center justify-center gap-2 rounded-xl text-sm text-[var(--text-secondary)]"><LogOut size={16} aria-hidden="true" />Sign out</button>
      </form>
    </section>
  </main>;
}
