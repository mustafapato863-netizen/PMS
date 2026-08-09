import { describe, expect, it } from 'vitest';
import type { AgentRecord } from '../types';
import { resolveAvailableTeamPeriods } from '../features/team/teamPeriods';

const record = (team: string, month: string, year?: number) => ({
  identity: { team, month },
  year,
}) as AgentRecord;

describe('resolveAvailableTeamPeriods', () => {
  it('only exposes periods belonging to the selected team', () => {
    const periods = resolveAvailableTeamPeriods([
      record('Pre-Approvals OP Dubai', 'May', 2026),
      record('Pre-Approvals OP Dubai', 'January', 2026),
      record('Inbound UAE', 'June', 2026),
    ], 'Pre-Approvals OP Dubai');

    expect(periods).toEqual([
      { month: 'January', year: 2026 },
      { month: 'May', year: 2026 },
    ]);
  });

  it('deduplicates periods and supplies the fallback year for legacy records', () => {
    const periods = resolveAvailableTeamPeriods([
      record('Pre-Approvals OP Dubai', 'May'),
      record('pre approvals op dubai', 'May'),
    ], 'Pre-Approvals OP Dubai', 2026);

    expect(periods).toEqual([{ month: 'May', year: 2026 }]);
  });
});
