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

describe('useActionStore deleteAction', () => {
  it('calls backend DELETE for UUID actionIds and only hides locally on success', async () => {
    const uuidId = '11111111-2222-3333-4444-555555555555';
    localStorage.setItem(
      'pms_actions_v2',
      JSON.stringify([
        {
          id: uuidId,
          employee_id: 'EMP-1',
          employee_name: 'Test Agent',
          team: 'Inbound',
          month: 'June',
          action_type: 'Coaching',
          action_text: 'Coach script',
          root_cause_note: '',
          created_at: '2026-06-01T00:00:00Z',
        },
      ]),
    );

    const { result } = renderHook(() => useActionStore(), { wrapper });

    let ok = false;
    await act(async () => {
      ok = await result.current.deleteAction(uuidId, 'EMP-1');
    });

    expect(ok).toBe(true);
    expect(apiFetch).toHaveBeenCalledWith(
      `/api/employee/EMP-1/corrective-actions/${uuidId}`,
      { method: 'DELETE' },
    );
    expect(JSON.parse(localStorage.getItem('pms_deleted_actions_v2') || '[]')).toContain(uuidId);
  });

  it('aborts local hiding and returns false when backend DELETE returns failure', async () => {
    const uuidId = '11111111-2222-3333-4444-666666666666';
    localStorage.setItem(
      'pms_actions_v2',
      JSON.stringify([
        {
          id: uuidId,
          employee_id: 'EMP-1',
          employee_name: 'Test Agent',
          team: 'Inbound',
          month: 'June',
          action_type: 'Coaching',
          action_text: 'Coach script',
          root_cause_note: '',
          created_at: '2026-06-01T00:00:00Z',
        },
      ]),
    );
    apiFetch.mockImplementation(async (_url, init) => {
      if (init?.method === 'DELETE') {
        return { success: false, data: [] };
      }
      return { success: true, data: [] };
    });

    const { result } = renderHook(() => useActionStore(), { wrapper });

    let ok = true;
    await act(async () => {
      ok = await result.current.deleteAction(uuidId, 'EMP-1');
    });

    apiFetch.mockReset();
    apiFetch.mockImplementation(async () => ({ success: true, data: [] }));

    expect(ok).toBe(false);
    expect(JSON.parse(localStorage.getItem('pms_deleted_actions_v2') || '[]')).not.toContain(uuidId);
    expect(JSON.parse(localStorage.getItem('pms_actions_v2') || '[]')).toHaveLength(1);
  });

  it('skips backend DELETE for non-UUID local IDs and removes locally', async () => {
    const localId = 'act-local-123';
    localStorage.setItem(
      'pms_actions_v2',
      JSON.stringify([
        {
          id: localId,
          employee_id: 'EMP-1',
          employee_name: 'Test Agent',
          team: 'Inbound',
          month: 'June',
          action_type: 'Coaching',
          action_text: 'Local note',
          root_cause_note: '',
          created_at: '2026-06-01T00:00:00Z',
        },
      ]),
    );

    const { result } = renderHook(() => useActionStore(), { wrapper });

    let ok = false;
    await act(async () => {
      ok = await result.current.deleteAction(localId, 'EMP-1');
    });

    expect(ok).toBe(true);
    const deleteCalls = apiFetch.mock.calls.filter(
      ([, init]) => (init as { method?: string })?.method === 'DELETE',
    );
    expect(deleteCalls).toHaveLength(0);
    expect(JSON.parse(localStorage.getItem('pms_deleted_actions_v2') || '[]')).toContain(localId);
  });
});
