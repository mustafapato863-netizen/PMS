import { describe, expect, it, vi } from 'vitest';
import { RateLimitError } from '../../lib/rateLimit';
import { ACCEPTANCE_UNKNOWN_NOTE, enqueueMonthlyApply, evaluationErrorText } from './evaluationApplyJobs';
import type { ReportingSelection } from './monthlyCorrection';

const selection: ReportingSelection = { scopeId: 'scope-1', year: 2026, month: 7 };

function httpJson(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('enqueueMonthlyApply rate limits', () => {
  it('reports a 429 on enqueue as the rate-limit message, without the acceptance note or a job lookup', async () => {
    const fetchWithRole = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'POST') throw new RateLimitError(7);
      return httpJson({ job: null });
    });

    const error = await enqueueMonthlyApply({ fetchWithRole, selection, recheck: false }).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(RateLimitError);
    expect(evaluationErrorText(error)).toBe('Too many requests. Try again in 7 seconds.');
    expect(evaluationErrorText(error)).not.toContain(ACCEPTANCE_UNKNOWN_NOTE);
    expect(fetchWithRole).toHaveBeenCalledTimes(1);
  });

  it('keeps the adopt path for other enqueue failures', async () => {
    const fetchWithRole = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'POST') throw new Error('socket down');
      return httpJson({ job: null });
    });

    await expect(enqueueMonthlyApply({ fetchWithRole, selection, recheck: false })).rejects.toThrow(ACCEPTANCE_UNKNOWN_NOTE);
    expect(fetchWithRole).toHaveBeenCalledTimes(2);
    expect(fetchWithRole.mock.calls[1]?.[1]?.method).toBeUndefined();
  });
});
