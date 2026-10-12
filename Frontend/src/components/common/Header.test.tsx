import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import Header from './Header';

vi.mock('../../context/RoleContext', () => ({
  useUserRole: () => ({ role: 'Admin', fetchWithRole: vi.fn() }),
}));

vi.mock('../../context/auth', () => ({
  useAuth: () => ({
    currentUser: { id: 'admin-1', name: 'Admin User', username: 'admin', role: 'Admin' },
    logout: vi.fn(),
  }),
}));

vi.mock('../../hooks/api/usePerformanceCatalog', () => ({
  usePerformanceCatalog: () => ({ data: undefined }),
}));

vi.mock('./GlobalSearch', () => ({ default: () => null }));
vi.mock('./ThemeToggle', () => ({ default: () => null }));
vi.mock('../notifications', () => ({ NotificationBell: () => null }));

function renderHeader(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Header onMenuClick={vi.fn()} />
    </MemoryRouter>,
  );
}

function headerTitle() {
  return document.querySelector('.app-header-title-full')?.textContent;
}

describe('Header title', () => {
  it.each(['/settings', '/settings/users', '/settings/evaluation?year=2026&month=8'])('shows the Administration title on %s', (path) => {
    renderHeader(path);
    expect(screen.getByText('Administration', { selector: '.app-header-title-full' })).toBeInTheDocument();
    expect(headerTitle()).toBe('Administration');
  });

  it('does not treat a path that only starts with /settings as Administration', () => {
    renderHeader('/settings-archive');
    expect(headerTitle()).not.toBe('Administration');
    expect(headerTitle()).toBe('Executive Summary');
  });
});
