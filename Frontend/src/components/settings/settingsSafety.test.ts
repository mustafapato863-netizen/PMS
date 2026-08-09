import { QueryClient } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import type { User } from '../../types';
import { mergeKPIConfig, refreshManagementData, safeUserName, userInitials } from './settingsUtils';

describe('settings runtime safety', () => {
  it('renders safe user labels when the API returns a null name', () => {
    const user = { name: null } as unknown as User;
    expect(safeUserName(user)).toBe('Unnamed user');
    expect(userInitials(user)).toBe('UU');
  });

  it('normalizes missing KPI records instead of reading null objects', () => {
    expect(mergeKPIConfig(
      [{ team: 'Coding', weights: null }],
      [{ team: 'Coding', targets: null }],
    )).toEqual([{ team: 'Coding', weights: {}, targets: {}, scopes: [] }]);
  });

  it('keeps position-scoped KPI definitions for multi-position teams', () => {
    expect(mergeKPIConfig(
      [{ team: 'Approvals', weights: {}, scopes: [
        { position: 'IP', weights: { rejection: 0.6 } },
        { position: 'ER', weights: { rejection: 0.6, tat: 0.4 } },
      ] }],
      [{ team: 'Approvals', targets: {}, scopes: [
        { position: 'IP', targets: { rejection: 3 } },
        { position: 'ER', targets: { rejection: 1, tat: 100 } },
      ] }],
    ).find((item) => item.team === 'Approvals')?.scopes).toEqual([
      { position: 'ER', weights: { rejection: 0.6, tat: 0.4 }, targets: { rejection: 1, tat: 100 } },
      { position: 'IP', weights: { rejection: 0.6 }, targets: { rejection: 3 } },
    ]);
  });

  it('reloads management uploads and invalidates balanced scorecard data together', async () => {
    const queryClient = new QueryClient();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries').mockResolvedValue();
    const reload = vi.fn().mockResolvedValue(undefined);

    await refreshManagementData(queryClient, reload);

    expect(reload).toHaveBeenCalledOnce();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['balanced-scorecard'] });
  });
});
