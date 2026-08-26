import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiErrorMessage, apiFetch, getAccessToken, setAccessToken, terminateClientSession } from './apiClient';
import { queryClient } from './queryClient';

beforeEach(() => {
  localStorage.clear();
  queryClient.clear();
});

afterEach(() => {
  localStorage.clear();
  queryClient.clear();
  setAccessToken(null);
  vi.unstubAllGlobals();
});

describe('apiErrorMessage', () => {
  it('turns FastAPI validation objects into readable field messages', () => {
    expect(apiErrorMessage({
      detail: [
        { loc: ['body', 'objectives', 0, 'name'], msg: 'String should have at least 3 characters' },
        { loc: ['body', 'owner_user_id'], msg: 'Input should be a valid UUID' },
      ],
    }, 422)).toBe(
      'objectives → name: String should have at least 3 characters · owner user id: Input should be a valid UUID',
    );
  });

  it('never renders an object as object Object', () => {
    const message = apiErrorMessage({ detail: { unexpected: true } }, 422);
    expect(message).toBe('Request failed (HTTP 422)');
    expect(message).not.toContain('[object Object]');
  });
});

describe('terminateClientSession', () => {
  it('removes stored authentication and all user-scoped query data', async () => {
    localStorage.setItem('pms_token', 'token');
    localStorage.setItem('pms_session_v1', '{"id":"user-1"}');
    localStorage.setItem('pms_user_role', 'Manager');
    queryClient.setQueryData(['performance', 'private'], { employee: 'private' });

    await terminateClientSession();

    expect(localStorage.getItem('pms_token')).toBeNull();
    expect(localStorage.getItem('pms_session_v1')).toBeNull();
    expect(localStorage.getItem('pms_user_role')).toBeNull();
    expect(queryClient.getQueryData(['performance', 'private'])).toBeUndefined();
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
    expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
  });
});

describe('apiFetch authentication recovery', () => {
  it('rotates the cookie session once and retries a request after a 401', async () => {
    setAccessToken('expired-access-token');
    localStorage.setItem('pms_csrf_token', 'csrf-token');
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'expired' }), { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        success: true,
        data: { access_token: 'fresh-access-token', csrf_token: 'fresh-csrf-token' },
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ success: true, data: { value: 42 } }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(apiFetch<{ success: boolean; data: { value: number } }>('/api/protected')).resolves.toEqual({
      success: true,
      data: { value: 42 },
    });
    expect(getAccessToken()).toBe('fresh-access-token');
    expect(localStorage.getItem('pms_csrf_token')).toBe('fresh-csrf-token');
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[1][1]).toMatchObject({
      method: 'POST',
      credentials: 'include',
      headers: { 'X-CSRF-Token': 'csrf-token' },
    });
    expect(fetchMock.mock.calls[2][1]?.headers).toMatchObject({
      Authorization: 'Bearer fresh-access-token',
    });
  });
});
