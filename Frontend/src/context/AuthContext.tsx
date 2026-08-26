import React, { useState, useEffect, useCallback } from 'react';
import type { User } from '../types';
import { apiFetch, getAccessToken, setAccessToken, terminateClientSession } from '../lib/apiClient';
import { AuthContext } from './auth';
import type { AuthContextProps } from './auth';

const SESSION_KEY = 'pms_session_v1';

const getActiveRole = () => localStorage.getItem('pms_user_role') || 'Viewer';

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [users, setUsers] = useState<User[]>([]);
  const [currentUser, setCurrentUser] = useState<User | null>(() => {
    const saved = localStorage.getItem(SESSION_KEY);
    if (saved) {
      try { return JSON.parse(saved) as User; } catch { /* Ignore invalid legacy session data. */ }
    }
    return null;
  });
  const [initializationStatus, setInitializationStatus] = useState<AuthContextProps['initializationStatus']>('authenticating');
  const [initializationError, setInitializationError] = useState<string | null>(null);
  const [authReady, setAuthReady] = useState(false);

  // Bootstrap from the HttpOnly refresh cookie. A legacy localStorage access
  // token is accepted once during migration, but no new long-lived token is
  // written there by this provider.
  useEffect(() => {
    const bootstrap = async () => {
      const token = getAccessToken();
      if (!token) {
        try {
          const refreshed = await apiFetch<{ success: boolean; data?: { access_token?: string } }>('/api/auth/refresh', { method: 'POST' });
          if (!refreshed.success || !refreshed.data?.access_token) throw new Error('No session');
          setAccessToken(refreshed.data.access_token);
        } catch {
          await terminateClientSession();
          setCurrentUser(null);
          setInitializationStatus('authenticating');
          return;
        }
      }
      setAuthReady(true);
      setInitializationStatus('loadingProfile');
    };
    void bootstrap();
  }, []);

  // Load profile, permissions, teams
  useEffect(() => {
    const load = async () => {
      if (!getAccessToken()) return;
      try {
        setInitializationStatus('loadingProfile');
        const meRes = await apiFetch<{ success: boolean; data?: Partial<User> }>('/api/auth/me');
        if (meRes.success && meRes.data) {
          setCurrentUser((previousUser) => {
            const user: User = { ...(previousUser ?? {}), ...meRes.data, id: meRes.data?.id || previousUser?.id || '' } as User;
            localStorage.setItem(SESSION_KEY, JSON.stringify(user));
            localStorage.setItem('pms_user_role', user.role);
            return user;
          });
          setInitializationStatus('loadingPermissions');
          // Permissions fetching omitted
          setInitializationStatus('loadingTeams');
          // Teams fetching omitted
          setInitializationStatus('loadingNavigation');
          setInitializationStatus('ready');
        } else {
          throw new Error('Profile load failed');
        }
      } catch {
        setInitializationError('Unable to prepare your workspace.');
        setInitializationStatus('error');
      }
    };
    load();
  }, [authReady]);

  const login = async (username: string, password: string, rememberMe = false) => {
    try {
      const res = await apiFetch<{ success: boolean; data?: { access_token: string; username: string; role: string }; message?: string }>('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password, remember_me: rememberMe }),
      });
      if (!res.success) return { success: false, error: res.message || 'Username or Password wrong' };
      const { access_token } = res.data!;
      const user: User = { id: '', name: res.data?.username || username, username: res.data?.username || username, role: (res.data?.role || 'Viewer') as User['role'] };
      setAccessToken(access_token);
      const csrfToken = (res.data as { csrf_token?: string } | undefined)?.csrf_token;
      if (csrfToken) localStorage.setItem('pms_csrf_token', csrfToken);
      setCurrentUser(user);
      setInitializationError(null);
      setInitializationStatus('loadingProfile');
      const me = await apiFetch<{ success: boolean; data?: Partial<User> }>('/api/auth/me');
      if (me.success && me.data) {
        const fullUser = { ...user, ...me.data, id: me.data.id || user.id } as User;
        setCurrentUser(fullUser);
        localStorage.setItem(SESSION_KEY, JSON.stringify(fullUser));
        localStorage.setItem('pms_user_role', fullUser.role);
      }
      setInitializationStatus('loadingPermissions');
      setInitializationStatus('loadingTeams');
      setInitializationStatus('loadingNavigation');
      setInitializationStatus('ready');
      return { success: true };
    } catch {
      return { success: false, error: 'Failed to connect to authentication server' };
    }
  };

  const logout = () => {
    apiFetch('/api/auth/logout', { method: 'POST' }).catch(() => {});
    void terminateClientSession();
    setCurrentUser(null);
    setUsers([]);
    setInitializationError(null);
    setInitializationStatus('authenticating');
  };

  const refreshUsers = useCallback(async () => {
    try {
      const res = await apiFetch<{ success: boolean; data?: User[] }>('/api/users/');
      if (res.success && res.data) setUsers(res.data);
    } catch (err) {
      console.error('Failed to refresh users', err);
    }
  }, []);

  const updateProfile = async (fullName: string) => {
    const normalized = fullName.trim();
    if (!normalized) return { success: false, error: 'Full name is required' };
    try {
      await apiFetch('/api/auth/profile', {
        method: 'PUT',
        body: JSON.stringify({ full_name: normalized }),
      });
      const me = await apiFetch<{ success: boolean; data?: Partial<User> }>('/api/auth/me');
      if (!me.success || !me.data) return { success: false, error: 'Profile updated, but refresh failed' };
      const refreshed = { ...currentUser, ...me.data, id: me.data.id || currentUser?.id || '' } as User;
      setCurrentUser(refreshed);
      localStorage.setItem(SESSION_KEY, JSON.stringify(refreshed));
      return { success: true };
    } catch (error: unknown) {
      return { success: false, error: error instanceof Error ? error.message : 'Failed to update profile' };
    }
  };

  const changePassword = async (currentPassword: string, newPassword: string) => {
    try {
      await apiFetch('/api/auth/profile/password', {
        method: 'POST',
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      return { success: true };
    } catch (error: unknown) {
      return { success: false, error: error instanceof Error ? error.message : 'Failed to change password' };
    }
  };

  const addUser = async (name: string, username: string, password: string, role: User['role'], accessibleTeams: string[] = [], isGeneralManager = false) => {
    const trimmed = username.trim().toLowerCase();
    if (!name || !trimmed || !password) return { success: false, error: 'All fields required' };
    if (!currentUser || getActiveRole() !== 'Admin') return { success: false, error: 'Only administrators can add users' };
    try {
      const res = await apiFetch<{ success: boolean; message?: string }>('/api/users/', {
        method: 'POST',
        body: JSON.stringify({ id: `user-${Date.now()}`, name: name.trim(), username: trimmed, password, role, accessible_teams: accessibleTeams, is_general_manager: isGeneralManager }),
      });
      if (res.success) { await refreshUsers(); return { success: true }; }
      return { success: false, error: res.message || 'Failed to create user' };
    } catch (error: unknown) { return { success: false, error: error instanceof Error ? error.message : 'Failed to connect to backend' }; }
  };

  const updateUser = async (id: string, patch: Partial<User> & { password?: string }) => {
    if (!currentUser || getActiveRole() !== 'Admin') return { success: false, error: 'Only administrators can update users' };
    try {
      const res = await apiFetch<{ success: boolean; message?: string }>(`/api/users/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ id, name: patch.name || '', username: patch.username || '', role: patch.role || 'Viewer', is_active: patch.is_active ?? true, accessible_teams: patch.accessible_teams ?? [], is_general_manager: patch.is_general_manager ?? false, ...(patch.password ? { password: patch.password } : {}) }),
      });
      if (res.success) { await refreshUsers(); return { success: true }; }
      return { success: false, error: res.message || 'Failed to update user' };
    } catch (error: unknown) { return { success: false, error: error instanceof Error ? error.message : 'Failed to connect to backend' }; }
  };

  const deleteUser = async (id: string) => {
    if (!currentUser || getActiveRole() !== 'Admin') return { success: false, error: 'Only administrators can delete users' };
    if (currentUser.id === id) return { success: false, error: 'Cannot delete your own logged-in account' };
    try {
      const res = await apiFetch<{ success: boolean; message?: string }>(`/api/users/${id}`, { method: 'DELETE' });
      if (res.success) { await refreshUsers(); return { success: true }; }
      return { success: false, error: res.message || 'Failed to delete user' };
    } catch (error: unknown) { return { success: false, error: error instanceof Error ? error.message : 'Failed to connect to backend' }; }
  };

  const toggleUserActive = async (id: string, isActive: boolean) => {
    if (!currentUser || getActiveRole() !== 'Admin') return { success: false, error: 'Only administrators can change user status' };
    if (currentUser.id === id && !isActive) return { success: false, error: 'Cannot deactivate your own account' };
    try {
      const res = await apiFetch<{ success: boolean; message?: string }>(`/api/users/${id}/toggle-active?is_active=${isActive}`, { method: 'POST' });
      if (res.success) { await refreshUsers(); return { success: true }; }
      return { success: false, error: res.message || 'Failed to change user status' };
    } catch (error: unknown) { return { success: false, error: error instanceof Error ? error.message : 'Failed to connect to backend' }; }
  };

  return (
    <AuthContext.Provider
      value={{
        currentUser,
        users,
        initializationStatus,
        isAppInitializing: ['authenticating','loadingProfile','loadingPermissions','loadingTeams'].includes(initializationStatus) && !!currentUser,
        initializationError,
        login,
        logout,
        updateProfile,
        changePassword,
        addUser,
        updateUser,
        deleteUser,
        toggleUserActive,
        refreshUsers,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};
