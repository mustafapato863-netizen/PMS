import React, { useState, useEffect, useCallback } from 'react';
import type { User } from '../types';
import { apiFetch, terminateClientSession } from '../lib/apiClient';
import { jwtDecode } from 'jwt-decode';
import { AuthContext } from './auth';
import type { AuthContextProps } from './auth';

interface JWTPayload {
  user_id: string;
  sub: string;
  role: string;
  username: string;
  exp: number;
}

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

  // Validate token on mount
  useEffect(() => {
    const token = localStorage.getItem('pms_token');
    if (!token) return;
    queueMicrotask(() => {
      try {
        const decoded = jwtDecode<JWTPayload>(token);
        if (decoded.exp * 1000 < Date.now()) throw new Error('Expired');
        setCurrentUser((previousUser) => {
          const normalized = previousUser
            ? { ...previousUser, id: previousUser.id || decoded.user_id }
            : { id: decoded.user_id, name: decoded.username, username: decoded.sub, role: decoded.role as User['role'] };
          localStorage.setItem(SESSION_KEY, JSON.stringify(normalized));
          localStorage.setItem('pms_user_role', normalized.role);
          return normalized;
        });
        setInitializationStatus('loadingProfile');
      } catch {
        void terminateClientSession();
        setCurrentUser(null);
        setInitializationStatus('authenticating');
      }
    });
  }, []);

  // Load profile, permissions, teams
  useEffect(() => {
    const load = async () => {
      const token = localStorage.getItem('pms_token');
      if (!token) return;
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
  }, []);

  const login = async (username: string, password: string) => {
    try {
      const res = await apiFetch<{ success: boolean; data?: { access_token: string; username: string; role: string }; message?: string }>('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      });
      if (!res.success) return { success: false, error: res.message || 'Username or Password wrong' };
      const { access_token } = res.data!;
      const decoded = jwtDecode<JWTPayload>(access_token);
      const user: User = { id: decoded.user_id, name: decoded.username, username: decoded.username, role: decoded.role as User['role'] };
      localStorage.setItem('pms_token', access_token);
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
