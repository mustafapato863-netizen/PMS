import type { ReactNode } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Header from '../../common/Header';
import { AiAvailabilityProvider } from '../../../features/ai/aiAvailability';
import { AiFeatureSwitch } from './AiFeatureSwitch';

const apiFetch = vi.hoisted(() => vi.fn());

vi.mock('../../../lib/apiClient', () => ({ apiFetch }));
vi.mock('../../../context/auth', () => ({
  useAuth: () => ({ currentUser: { id: 'admin-1', role: 'Admin', name: 'Admin' }, logout: vi.fn() }),
}));
vi.mock('../../../context/RoleContext', () => ({
  useUserRole: () => ({ role: 'Admin', fetchWithRole: vi.fn() }),
}));
vi.mock('../../../hooks/api/usePerformanceCatalog', () => ({
  usePerformanceCatalog: () => ({ data: undefined }),
}));
vi.mock('../../common/GlobalSearch', () => ({ default: () => null }));
vi.mock('../../common/ThemeToggle', () => ({ default: () => null }));
vi.mock('../../notifications', () => ({ NotificationBell: () => null }));

function renderWithAvailability(ui: ReactNode) {
  return render(<MemoryRouter><AiAvailabilityProvider>{ui}</AiAvailabilityProvider></MemoryRouter>);
}

describe('PMS AI administrator switch', () => {
  beforeEach(() => {
    apiFetch.mockReset();
    apiFetch.mockImplementation((_url: string, options?: { method?: string }) => {
      if (options?.method === 'PUT') return Promise.resolve({ success: true, data: { enabled: true } });
      return Promise.resolve({ success: true, data: { enabled: false } });
    });
  });

  it('hides Ask AI for an administrator while the switch is off', async () => {
    apiFetch.mockResolvedValue({ success: true, data: { enabled: false } });
    renderWithAvailability(
      <>
        <AiFeatureSwitch />
        <Header onMenuClick={vi.fn()} />
      </>,
    );
    expect(await screen.findByRole('switch', { name: 'Enable PMS AI' })).toHaveAttribute('aria-checked', 'false');
    expect(screen.queryByRole('button', { name: 'Ask AI analytical assistant' })).not.toBeInTheDocument();
  });

  it('shows Ask AI after an administrator turns the switch on', async () => {
    renderWithAvailability(
      <>
        <AiFeatureSwitch />
        <Header onMenuClick={vi.fn()} />
      </>,
    );
    const toggle = await screen.findByRole('switch', { name: 'Enable PMS AI' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('button', { name: 'Ask AI analytical assistant' })).toBeInTheDocument();
    expect(apiFetch).toHaveBeenLastCalledWith('/api/settings/ai-assistant', expect.objectContaining({ method: 'PUT' }));
  });
});
