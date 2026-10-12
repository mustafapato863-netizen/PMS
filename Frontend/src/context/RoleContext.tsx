import React, { createContext, useContext, useCallback } from 'react';
import { useAuth } from './auth';
import { getAccessToken } from '../lib/apiClient';
import { RATE_LIMIT_STATUS, rejectRateLimited } from '../lib/rateLimit';
import type { User } from '../types';

export type UserRole = User['role'];

interface RoleContextProps {
  role: UserRole;
  setRole: (role: UserRole) => void;
  fetchWithRole: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
}

const RoleContext = createContext<RoleContextProps | undefined>(undefined);

export const RoleProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { currentUser } = useAuth();
  
  const role: UserRole = currentUser?.role ?? 'Employee';

  const setRole = (newRole: UserRole) => {
    localStorage.setItem('pms_user_role', newRole);
  };

  const fetchWithRole = useCallback(async (input: RequestInfo | URL, init?: RequestInit) => {
    const headers = new Headers(init?.headers);
    const token = getAccessToken();
    // Authenticated requests are authorized from the JWT on the backend. The
    // header remains only for local legacy-mode compatibility.
    if (!token && import.meta.env.DEV) headers.set('X-User-Role', role);
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }
    const response = await fetch(input, { ...init, headers, credentials: 'include' });
    // Callers read the response shape themselves. A 429 is not a shape they can handle, so it becomes a typed error.
    if (response.status === RATE_LIMIT_STATUS) throw rejectRateLimited(response, { notify: true });
    return response;
  }, [role]);

  return (
    <RoleContext.Provider value={{ role, setRole, fetchWithRole }}>
      {children}
    </RoleContext.Provider>
  );
};

/* eslint-disable-next-line react-refresh/only-export-components */
export const useUserRole = () => {
  const context = useContext(RoleContext);
  if (!context) {
    throw new Error('useUserRole must be used within a RoleProvider');
  }
  return context;
};

