import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { apiErrorMessage, terminateClientSession } from './apiClient';
import { queryClient } from './queryClient';

beforeEach(() => {
  localStorage.clear();
  queryClient.clear();
});

afterEach(() => {
  localStorage.clear();
  queryClient.clear();
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
