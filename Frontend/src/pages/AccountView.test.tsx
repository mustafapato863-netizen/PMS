import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { User } from '../types';
import { ThemeProvider } from '../context/ThemeContext';
import AccountView from './AccountView';

const state = vi.hoisted(() => ({
  user: { id: 'account-1', name: 'RCM Director', username: 'rcm', role: 'Function Director', accessible_functions: ['RCM'] } as User,
  updateProfile: vi.fn(), changePassword: vi.fn(), logout: vi.fn(), success: vi.fn(),
}));
vi.mock('../context/auth', () => ({ useAuth: () => ({ currentUser: state.user, updateProfile: state.updateProfile, changePassword: state.changePassword, logout: state.logout }) }));
vi.mock('../hooks/useToast', () => ({ useToast: () => ({ toast: { success: state.success } }) }));

const show = () => render(<MemoryRouter initialEntries={['/account']}><ThemeProvider><Routes>
  <Route path="/account" element={<AccountView />} />
  <Route path="/login" element={<p>Sign in again</p>} />
</Routes></ThemeProvider></MemoryRouter>);

describe('personal account settings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    state.user = { id: 'account-1', name: 'RCM Director', username: 'rcm', role: 'Function Director', accessible_functions: ['RCM'] };
    state.updateProfile.mockResolvedValue({ success: true });
    state.changePassword.mockResolvedValue({ success: true });
  });

  it.each<User['role']>(['Admin', 'Manager', 'Employee', 'Performance Team', 'Regional Manager', 'Branch Director', 'Function Director', 'General Manager', 'Executive', 'Viewer', 'Agent', 'Function Viewer'])('allows %s to manage only their personal profile', role => {
    state.user = { ...state.user, role };
    show();
    expect(screen.getByRole('heading', { name: 'Account settings' })).toBeInTheDocument();
    expect(screen.getByLabelText('Username')).toHaveAttribute('readonly');
    expect(screen.getByLabelText('Full name')).toHaveValue('RCM Director');
    expect(screen.queryByRole('link', { name: 'Open administration' }) !== null).toBe(role === 'Admin');
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('shows the assigned function without allowing it to be changed', () => {
    show();
    expect(screen.getByText('Functions: RCM')).toBeInTheDocument();
    expect(screen.getByText(/Personal settings do not change your data access/)).toBeInTheDocument();
  });

  it('updates only the current user display name through self-service', async () => {
    const actor = userEvent.setup();
    show();
    await actor.clear(screen.getByLabelText('Full name'));
    await actor.type(screen.getByLabelText('Full name'), '  RCM Lead  ');
    await actor.click(screen.getByRole('button', { name: 'Save name' }));
    expect(state.updateProfile).toHaveBeenCalledWith('RCM Lead');
    expect(await screen.findByRole('status')).toHaveTextContent('Full name updated successfully');
  });

  it('keeps the user on the page and exposes password API validation errors', async () => {
    state.changePassword.mockResolvedValue({ success: false, error: 'Current password is incorrect.' });
    const actor = userEvent.setup();
    show();
    await actor.type(screen.getByLabelText('Current password'), 'OldPassword123!');
    await actor.type(screen.getByLabelText('New password'), 'NewPassword456!');
    await actor.type(screen.getByLabelText('Confirm new password'), 'NewPassword456!');
    await actor.click(screen.getByRole('button', { name: 'Change password' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Current password is incorrect.');
    expect(state.logout).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Change password' })).toBeEnabled();
  });

  it('signs out and returns to login after a successful password change', async () => {
    const actor = userEvent.setup();
    show();
    await actor.type(screen.getByLabelText('Current password'), 'OldPassword123!');
    await actor.type(screen.getByLabelText('New password'), 'NewPassword456!');
    await actor.type(screen.getByLabelText('Confirm new password'), 'NewPassword456!');
    await actor.click(screen.getByRole('button', { name: 'Change password' }));
    expect(state.changePassword).toHaveBeenCalledWith('OldPassword123!', 'NewPassword456!');
    expect(state.logout).toHaveBeenCalledOnce();
    expect(await screen.findByText('Sign in again')).toBeInTheDocument();
  });

  it('selects and remembers the browser appearance without a profile API write', async () => {
    show();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Dark' }));
    expect(screen.getByRole('button', { name: 'Dark' })).toHaveAttribute('aria-pressed', 'true');
    expect(localStorage.getItem('pms_theme')).toBe('dark');
    expect(state.updateProfile).not.toHaveBeenCalled();
  });

  it('recovers from a rejected profile request', async () => {
    state.updateProfile.mockRejectedValue(new Error('Offline'));
    show();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Save name' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to save your name');
    expect(screen.getByRole('button', { name: 'Save name' })).toBeEnabled();
  });
});
