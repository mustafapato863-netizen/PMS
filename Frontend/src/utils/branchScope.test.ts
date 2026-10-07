import { describe, expect, it } from 'vitest';
import { agentMatchesLocation } from './branchScope';
import { mapScopedPerformanceRecord } from '../hooks/usePerformanceData';

describe('canonical branch display', () => {
  it('keeps the canonical branch through record mapping and ignores conflicting legacy metadata', () => {
    const agent = mapScopedPerformanceRecord({
      branch_key: 'Dubai', employee_id: 'E1', employee_name: 'One', team: 'Inbound', month: 'June',
      raw_data: { Branch: 'Sharjah' }, geo: { bookings: { sharjah: 10 } },
    });
    expect(agent.branch_key).toBe('Dubai');
    expect(agentMatchesLocation(agent, 'dubai')).toBe(true);
    expect(agentMatchesLocation(agent, 'sharjah')).toBe(false);
    expect(agentMatchesLocation(agent, 'all')).toBe(true);
  });
});
