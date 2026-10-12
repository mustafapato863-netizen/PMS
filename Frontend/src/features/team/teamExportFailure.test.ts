import { describe, expect, it } from 'vitest';
import { RateLimitError } from '../../lib/rateLimit';
import { teamExportFailureAlert } from './teamExportFailure';

describe('teamExportFailureAlert', () => {
  it('shows no second message for a rate-limited export', () => {
    expect(teamExportFailureAlert(new RateLimitError(5))).toBeNull();
  });

  it('keeps the offline message for every other failure', () => {
    expect(teamExportFailureAlert(new TypeError('Failed to fetch'))).toBe('Export failed: backend offline.');
    expect(teamExportFailureAlert('boom')).toBe('Export failed: backend offline.');
  });
});
