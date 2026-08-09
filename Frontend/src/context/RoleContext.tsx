import React, { createContext, useContext, useCallback } from 'react';
import { useAuth } from './auth';

export type UserRole = 'Admin' | 'Manager' | 'Executive' | 'Viewer' | 'Agent';

interface RoleContextProps {
  role: UserRole;
  setRole: (role: UserRole) => void;
  fetchWithRole: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
}

const RoleContext = createContext<RoleContextProps | undefined>(undefined);

export const RoleProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { currentUser } = useAuth();
  
  const role: UserRole = currentUser?.role ?? 'Viewer';

  const setRole = (newRole: UserRole) => {
    localStorage.setItem('pms_user_role', newRole);
  };

  const fetchWithRole = useCallback(async (input: RequestInfo | URL, init?: RequestInit) => {
    const headers = new Headers(init?.headers);
    headers.set('X-User-Role', role);
    const token = localStorage.getItem('pms_token');
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }
    return fetch(input, { ...init, headers });
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

