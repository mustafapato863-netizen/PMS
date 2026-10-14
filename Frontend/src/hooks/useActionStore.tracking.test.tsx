import { act, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useActionStore } from './useActionStore';

const { apiFetch } = vi.hoisted(() => ({
  apiFetch: vi.fn<(url: string, init?: { method?: string; body?: string }) => Promise<{ success: boolean; data: unknown[] }>>(async () => ({ success: true, data: [] })),
}));

vi.mock('../lib/apiClient', () => ({ apiFetch }));
vi.mock('../context/RoleContext', () => ({ useUserRole: () => ({ role: 'Admin', fetchWithRole: vi.fn() }) }));
vi.mock('../context/auth', () => ({
  useAuth: () => ({ currentUser: { id: 'owner-1', name: 'Hany Mostafa', role: 'Admin' } }),
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

/** Bodies sent to the employee corrective-action endpoint (create and update share it). */
function sentBodies(): Array<Record<string, unknown>> {
  return apiFetch.mock.calls
    .filter(([url, init]) => String(url).startsWith('/api/employee/') && (init as { method?: string })?.method === 'POST')
    .map(([, init]) => JSON.parse(String((init as { body?: string }).body)) as Record<string, unknown>);
}

beforeEach(() => {
  apiFetch.mockClear();
  localStorage.clear();
});

describe('useActionStore update requests', () => {
  it('sends only the tracking fields it was given, so an absent field is not sent as null', async () => {
    const { result } = renderHook(() => useActionStore(), { wrapper });

    await act(async () => {
      await result.current.updateAction('act-1', { action_text: 'Coach the booking script', due_date: undefined }, { id: 'EMP-1', name: 'Test Agent', team: 'Inbound' }, 'June');
    });

    const [body] = sentBodies();
    expect(body).toMatchObject({ id: 'act-1', month: 'June' });
    expect(body).not.toHaveProperty('due_date');
    expect(body).not.toHaveProperty('owner_user_id');
    expect(body).not.toHaveProperty('priority');
  });

  it('passes an explicit null through, which is how a field is cleared', async () => {
    const { result } = renderHook(() => useActionStore(), { wrapper });

    await act(async () => {
      await result.current.updateAction('act-1', { owner_user_id: null, due_date: null }, { id: 'EMP-1', name: 'Test Agent', team: 'Inbound' }, 'June');
    });

    const [body] = sentBodies();
    expect(body).toHaveProperty('owner_user_id', null);
    expect(body).toHaveProperty('due_date', null);
    expect(body).not.toHaveProperty('priority');
  });
});
