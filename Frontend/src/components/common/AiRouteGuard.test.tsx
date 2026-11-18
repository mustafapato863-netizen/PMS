import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { useAuth } from '../../context/auth';
import { AiRouteGuard } from './AiRouteGuard';

vi.mock('../../context/auth', () => ({ useAuth: vi.fn() }));
const mockedUseAuth = vi.mocked(useAuth);

function renderGuard(currentUser: unknown) {
  mockedUseAuth.mockReturnValue({ currentUser } as never);
  return render(
    <MemoryRouter initialEntries={['/ai']}>
      <Routes>
        <Route path="/ai" element={<AiRouteGuard><div>AI Workspace</div></AiRouteGuard>} />
        <Route path="/executive" element={<div>Executive</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('AiRouteGuard', () => {
  it('allows Admin in admin_only tier', () => {
    renderGuard({ role: 'Admin', ai_access_tier: 'admin_only' });
    expect(screen.getByText('AI Workspace')).toBeInTheDocument();
  });

  it('blocks Manager in admin_only tier', () => {
    renderGuard({ role: 'Manager', ai_access_tier: 'admin_only' });
    expect(screen.getByText('Executive')).toBeInTheDocument();
  });

  it('allows Manager in managers_and_admins tier', () => {
    renderGuard({ role: 'Manager', ai_access_tier: 'managers_and_admins' });
    expect(screen.getByText('AI Workspace')).toBeInTheDocument();
  });

  it('allows Agent in all_authenticated_users tier', () => {
    renderGuard({ role: 'Agent', ai_access_tier: 'all_authenticated_users' });
    expect(screen.getByText('AI Workspace')).toBeInTheDocument();
  });
});
