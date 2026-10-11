import { describe, expect, it } from 'vitest';
import { readColumnWarnings } from './uploadHeaderNotices';

describe('readColumnWarnings', () => {
  it('keeps known sheet notices and drops padding, unknown codes, and empty names', () => {
    const notices = readColumnWarnings([
      null,
      { code: 'ignored', sheet: 'Outbound', headers: ['Nope'] },
      { code: 'unmapped_columns', sheet: '   ', headers: ['', 'Side Note'] },
      { code: 'optional_columns', sheet: 'Outbound', headers: ['Productivity'] },
    ]);

    expect(notices).toEqual([
      { code: 'unmapped_columns', sheet: 'Sheet', headers: ['Side Note'], truncated: false },
      { code: 'optional_columns', sheet: 'Outbound', headers: ['Productivity'], truncated: false },
    ]);
  });

  it('bounds the notice list and marks a trimmed header list', () => {
    const headers = Array.from({ length: 30 }, (_item, index) => `Extra ${index + 1}`);
    const source = Array.from({ length: 14 }, (_item, index) => ({
      code: 'unmapped_columns',
      sheet: `Sheet ${index + 1}`,
      headers,
      truncated: false,
    }));

    const notices = readColumnWarnings(source);

    expect(notices).toHaveLength(12);
    expect(notices[0].headers).toHaveLength(25);
    expect(notices[0].headers[0]).toBe('Extra 1');
    expect(notices[0].truncated).toBe(true);
    expect(notices[0].sheet).toBe('Sheet 1');
  });
});
