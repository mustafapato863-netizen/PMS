import { afterEach, describe, expect, it } from 'vitest';
import { performanceSessionKey } from './performanceSessionKey';

afterEach(() => localStorage.removeItem('pms_session_v1'));

describe('performance cache scope', () => {
  it('changes when the same user role or grants change, not when grants are reordered', () => {
    const save = (role: string, branches: string[]) => {
      localStorage.setItem('pms_session_v1', JSON.stringify({ id: 'director', role, accessible_branches: branches }));
      return performanceSessionKey();
    };
    const first = save('Branch Director', ['dubai', 'sharjah']);
    expect(save('Branch Director', ['sharjah', 'dubai', 'dubai'])).toBe(first);
    expect(save('Branch Director', ['sharjah'])).not.toBe(first);
    expect(save('Admin', ['dubai', 'sharjah'])).not.toBe(first);
  });

  it('does not include credentials and tolerates invalid stored sessions', () => {
    localStorage.setItem('pms_session_v1', JSON.stringify({ id: '1', password: 'excluded-secret' }));
    expect(performanceSessionKey()).not.toContain('excluded-secret');
    for (const saved of ['null', '[]', 'invalid']) {
      localStorage.setItem('pms_session_v1', saved);
      expect(performanceSessionKey()).toBe('anonymous');
    }
  });
});
