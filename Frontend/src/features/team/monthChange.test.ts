import { describe, expect, it } from 'vitest';
import { formatMonthChange, missingMonthChangeText } from './monthChange';

describe('formatMonthChange', () => {
  it('shows a percentage KPI as points with the month', () => {
    expect(formatMonthChange(-0.94, '%', 'Aug')).toBe('−0.94 pts vs Aug');
    expect(formatMonthChange(0.5, '%', 'Aug')).toBe('+0.50 pts vs Aug');
  });

  it('uses one decimal for a percentage change of a point or more', () => {
    expect(formatMonthChange(3.3, '%', 'Jun')).toBe('+3.3 pts vs Jun');
    expect(formatMonthChange(-12.25, '%', 'Jun')).toBe('−12.3 pts vs Jun');
  });

  it('shows counts in their own unit with no unit suffix', () => {
    expect(formatMonthChange(12, undefined, 'Aug')).toBe('+12 vs Aug');
    expect(formatMonthChange(-3, 'number', 'Aug')).toBe('−3 vs Aug');
  });

  it('shows minutes, seconds and currency in their unit', () => {
    expect(formatMonthChange(1.5, 'min', 'Aug')).toBe('+1.5 min vs Aug');
    expect(formatMonthChange(-12.4, 's', 'Aug')).toBe('−12s vs Aug');
    expect(formatMonthChange(12.5, 'currency', 'Aug')).toBe('+AED 12.5 vs Aug');
  });

  it('shows no sign for no change', () => {
    expect(formatMonthChange(0, '%', 'Aug')).toBe('0.00 pts vs Aug');
  });
});

describe('missingMonthChangeText', () => {
  it('says there is no previous month when none has data', () => {
    expect(missingMonthChangeText(false)).toBe('No previous month');
  });

  it('says the KPI has no previous value when the previous month has data without it', () => {
    expect(missingMonthChangeText(true)).toBe('No previous value');
  });
});
