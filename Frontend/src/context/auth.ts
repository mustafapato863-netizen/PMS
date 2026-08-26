import { createContext, useContext } from 'react';
import type { User } from '../types';

export interface AuthContextProps {
  currentUser: User | null;
  users: User[];
  initializationStatus: 'authenticating' | 'loadingProfile' | 'loadingPermissions' | 'loadingTeams' | 'loadingNavigation' | 'ready' | 'error';
  isAppInitializing: boolean;
  initializationError: string | null;
  login: (username: string, password: string, rememberMe?: boolean) => Promise<{ success: boolean; error?: string }>;
  logout: () => void;
  updateProfile: (fullName: string) => Promise<{ success: boolean; error?: string }>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<{ success: boolean; error?: string }>;
  addUser: (name: string, username: string, password: string, role: User['role'], accessibleTeams?: string[], isGeneralManager?: boolean) => Promise<{ success: boolean; error?: string }>;
  updateUser: (id: string, patch: Partial<User> & { password?: string }) => Promise<{ success: boolean; error?: string }>;
  deleteUser: (id: string) => Promise<{ success: boolean; error?: string }>;
  toggleUserActive: (id: string, isActive: boolean) => Promise<{ success: boolean; error?: string }>;
  refreshUsers: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextProps | undefined>(undefined);

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
}
