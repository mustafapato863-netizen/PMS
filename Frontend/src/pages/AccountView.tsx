import { KeyRound, Moon, ShieldCheck, Sun, UserRound } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/auth';
import { useTheme } from '../context/ThemeContext';
import { ProfileSettingsForms } from '../components/common/ProfileSettingsModal';
import { canAccessSettingsContent, getRoleDisplayLabel, readHasUnrestrictedTeamAccess } from '../lib/access';
import { directorScope } from '../lib/directorScope';
import { useToast } from '../hooks/useToast';

export default function AccountView() {
  const { currentUser, updateProfile, changePassword, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const { toast } = useToast();
  const navigate = useNavigate();
  if (!currentUser) return null;
  const scope = directorScope(currentUser.role, currentUser);
  const scopeLabel = scope.branchLocked ? `Branches: ${scope.branchLabel}`
    : scope.regionLocked ? `Regions: ${scope.regionLabel}`
      : scope.functionLocked || currentUser.role === 'Function Viewer' ? `Functions: ${scope.functions.join(', ') || 'No function assigned'}`
        : currentUser.role === 'Employee' || currentUser.role === 'Agent' ? 'Your own employee profile and performance data only.'
          : currentUser.role === 'Manager' && !readHasUnrestrictedTeamAccess(currentUser) ? `Teams: ${currentUser.accessible_teams?.join(', ') || 'No team assigned'}`
            : 'Data access follows your role and administrator-assigned permissions.';

  const updatePassword = async (currentPassword: string, newPassword: string) => {
    const result = await changePassword(currentPassword, newPassword);
    if (result.success) {
      // The API revokes all sessions after ANY password change, not only first login.
      toast.success('Password updated. Sign in with your new password.', 8000);
      logout();
      navigate('/login', { replace: true });
    }
    return result;
  };

  return <div className="app-page-shell account-page">
    <header className="flex min-w-0 items-center gap-3">
      <span className="rounded-2xl bg-cyan-500/10 p-3 text-[var(--sgh-cyan-primary)]"><UserRound size={24} aria-hidden="true" /></span>
      <div className="min-w-0"><h1 className="text-2xl font-extrabold text-[var(--text-primary)]">Account settings</h1><p className="mt-1 text-sm text-[var(--text-secondary)]">Your profile, password and workspace appearance.</p></div>
    </header>
    <div className="grid min-w-0 items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(260px,340px)]">
      <section aria-label="Personal settings" className="min-w-0 rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4 sm:p-6">
        <ProfileSettingsForms key={currentUser.id} user={currentUser} onUpdateProfile={updateProfile} onChangePassword={updatePassword} />
      </section>
      <div className="grid min-w-0 gap-5">
        <section aria-labelledby="account-access-title" className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-5">
          <ShieldCheck size={22} className="mb-3 text-[var(--sgh-emerald-primary)]" aria-hidden="true" />
          <h2 id="account-access-title" className="font-bold text-[var(--text-primary)]">Your access</h2>
          <p className="mt-2 text-sm font-semibold text-[var(--text-primary)]">{getRoleDisplayLabel(currentUser.role)}</p>
          <p className="mt-2 break-words text-sm text-[var(--text-secondary)]">{scopeLabel}</p>
          <p className="mt-3 text-xs text-[var(--text-muted)]">Your administrator manages your role and assigned scope. Personal settings do not change your data access.</p>
          {canAccessSettingsContent(currentUser.role) && <Link to="/settings" className="mt-4 inline-flex min-h-11 items-center gap-2 rounded-xl border border-[var(--border-light)] px-3 text-sm font-semibold text-[var(--sgh-cyan-primary)]"><KeyRound size={16} aria-hidden="true" />Open administration</Link>}
        </section>
        <section aria-labelledby="account-appearance-title" className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-5">
          <h2 id="account-appearance-title" className="font-bold text-[var(--text-primary)]">Appearance</h2>
          <p className="mt-1 text-xs text-[var(--text-muted)]">Choose a comfortable theme. Saved on this browser.</p>
          <div className="mt-4 grid grid-cols-2 gap-2" role="group" aria-label="Color theme">
            {(['light', 'dark'] as const).map(value => <button key={value} type="button" aria-pressed={theme === value} onClick={() => setTheme(value)} className={`flex min-h-11 items-center justify-center gap-2 rounded-xl border text-sm font-semibold focus-visible:outline-2 focus-visible:outline-[var(--sgh-cyan-primary)] ${theme === value ? 'border-[var(--sgh-cyan-primary)] bg-cyan-500/10 text-[var(--sgh-cyan-primary)]' : 'border-[var(--border-light)] text-[var(--text-secondary)]'}`}>
              {value === 'light' ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}{value === 'light' ? 'Light' : 'Dark'}
            </button>)}
          </div>
        </section>
        <p className="px-1 text-xs leading-relaxed text-[var(--text-muted)]">Changing your password signs you out on all devices. You will sign in again with the new password.</p>
      </div>
    </div>
  </div>;
}
