import { render, renderHook, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { User } from '../../types';
import { useFunctionScope } from './useFunctionScope';
import FunctionScopeNotice from '../../components/common/FunctionScopeNotice';

const state = vi.hoisted(() => ({ role: 'Function Viewer' as string, user: null as Partial<User> | null }));
vi.mock('../../context/RoleContext', () => ({ useUserRole: () => ({ role: state.role }) }));
vi.mock('../../context/auth', () => ({ useAuth: () => ({ currentUser: state.user }) }));

beforeEach(() => {
  state.role = 'Function Viewer';
  state.user = { id: 'fv', name: 'Laila', role: 'Function Viewer', accessible_functions: ['RCM'] };
});

describe('useFunctionScope (team dashboard / employee profile guard)', () => {
  it('restricts a Function Viewer to teams in its functions', () => {
    const { result } = renderHook(() => useFunctionScope());
    expect(result.current.restricted).toBe(true);
    expect(result.current.allowed).toEqual(['RCM']);
    expect(result.current.allowsTeam('Coding')).toBe(true);
    expect(result.current.allowsTeam('Pre-Approvals IP Offshore')).toBe(true);
    expect(result.current.allowsTeam('Inbound')).toBe(false);
    expect(result.current.allowsTeam('Marketing')).toBe(false);
  });

  it('leaves every other role on its existing scoping', () => {
    for (const role of ['Admin', 'General Manager', 'Manager', 'Executive', 'Viewer']) {
      state.role = role;
      const { result } = renderHook(() => useFunctionScope());
      expect(result.current.restricted).toBe(false);
      expect(result.current.allowsTeam('Inbound')).toBe(true);
    }
  });

  it('renders a "Not in your functions" notice with a way back', () => {
    render(<MemoryRouter><FunctionScopeNotice subject="Hany (Inbound)" allowed={['RCM']} /></MemoryRouter>);
    expect(screen.getByRole('alert')).toHaveTextContent('Not in your functions');
    expect(screen.getByRole('alert')).toHaveTextContent('Hany (Inbound) is outside RCM');
    expect(screen.getByRole('link', { name: 'Back to Function Summary' })).toHaveAttribute('href', '/function-summary/rcm');
  });
});
