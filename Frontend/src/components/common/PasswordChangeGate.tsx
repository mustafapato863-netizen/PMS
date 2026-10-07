import type { ReactNode } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { useAuth } from '../../context/auth';
import FirstLoginPasswordChange from '../../pages/FirstLoginPasswordChange';

/** Blocks every workspace route, including direct URLs and browser history. */
export default function PasswordChangeGate({ children }: { children: ReactNode }) {
  const { currentUser } = useAuth();
  if (!currentUser?.must_change_password) return children;
  return <Routes>
    <Route path="/change-password" element={<FirstLoginPasswordChange />} />
    <Route path="*" element={<Navigate to="/change-password" replace />} />
  </Routes>;
}
