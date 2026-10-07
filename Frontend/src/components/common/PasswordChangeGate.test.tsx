import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useSyncExternalStore } from 'react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PasswordChangeGate from './PasswordChangeGate';

const auth = vi.hoisted(() => ({
  user: { id: 'new', name: 'New User', username: 'new', role: 'Admin', must_change_password: true } as { id: string; name: string; username: string; role: string; must_change_password: boolean } | null,
  changePassword: vi.fn(),
  logout: vi.fn(),
  success: vi.fn(),
  listeners: new Set<() => void>(),
}));
vi.mock('../../context/auth', () => ({
  useAuth: () => {
    // Match the provider's reactive logout, not a silently mutated mock snapshot.
    const currentUser = useSyncExternalStore(
      (listener) => {
        auth.listeners.add(listener);
        return () => { auth.listeners.delete(listener); };
      },
      () => auth.user,
    );
    return { currentUser, changePassword: auth.changePassword, logout: auth.logout };
  },
}));
vi.mock('../../hooks/useToast', () => ({ useToast: () => ({ toast: { success: auth.success } }) }));

function Location() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}</output>;
}
function renderGate(path = '/executive') {
  return render(<MemoryRouter initialEntries={[path]}>
    <PasswordChangeGate><div data-testid="workspace">Workspace data</div></PasswordChangeGate>
    <Location />
  </MemoryRouter>);
}
function fill(newPassword = 'PersonalPassword456!', confirm = newPassword) {
  fireEvent.change(screen.getByLabelText('Temporary password'), { target: { value: 'TemporaryPassword123!' } });
  fireEvent.change(screen.getByLabelText('New password'), { target: { value: newPassword } });
  fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: confirm } });
  fireEvent.click(screen.getByRole('button', { name: 'Set password and sign in' }));
}

beforeEach(() => {
  vi.clearAllMocks();
  auth.user = { id: 'new', name: 'New User', username: 'new', role: 'Admin', must_change_password: true };
  auth.logout.mockImplementation(() => {
    auth.user = null;
    auth.listeners.forEach((listener) => listener());
  });
});
describe('First-login password gate', () => {
  it.each(['/executive', '/settings', '/reports', '/team/coding', '/employee/one', '/change-password'])('blocks direct access to %s', (path) => {
    renderGate(path);
    expect(screen.queryByTestId('workspace')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Secure your account' })).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('/change-password');
    expect(screen.queryByRole('button', { name: /cancel|close|skip/i })).not.toBeInTheDocument();
  });
  it('does not interrupt an existing account', () => {
    auth.user!.must_change_password = false;
    renderGate();
    expect(screen.getByTestId('workspace')).toBeInTheDocument();
  });
  it('rejects mismatched confirmation without sending passwords', () => {
    renderGate();
    fill('PersonalPassword456!', 'DifferentPassword789!');
    expect(screen.getByRole('alert')).toHaveTextContent('do not match');
    expect(auth.changePassword).not.toHaveBeenCalled();
  });
  it('rejects reuse of the temporary password', () => {
    renderGate();
    fill('TemporaryPassword123!');
    expect(screen.getByRole('alert')).toHaveTextContent('different');
    expect(auth.changePassword).not.toHaveBeenCalled();
  });
  it('keeps the gate closed on a server validation error', async () => {
    auth.changePassword.mockResolvedValue({ success: false, error: 'Current password is incorrect.' });
    renderGate();
    fill();
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Current password is incorrect.'));
    expect(auth.logout).not.toHaveBeenCalled();
    expect(screen.queryByTestId('workspace')).not.toBeInTheDocument();
  });
  it('returns to sign-in after a successful password change', async () => {
    auth.changePassword.mockResolvedValue({ success: true });
    renderGate();
    fill();
    await waitFor(() => expect(auth.logout).toHaveBeenCalledOnce());
    expect(auth.changePassword).toHaveBeenCalledWith('TemporaryPassword123!', 'PersonalPassword456!');
    expect(auth.success).toHaveBeenCalledWith('Password updated. Sign in with your new password.', 8000);
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/login'));
  });
  it('lets the user sign out without unlocking the account', () => {
    renderGate();
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(auth.logout).toHaveBeenCalledOnce();
    expect(auth.changePassword).not.toHaveBeenCalled();
  });
});
