import { describe, expect, it } from 'vitest';

import type { EvaluationLine } from './evaluationSettings';
import {
  commitLineInputs,
  formatIdentifiedTarget,
  inputToStoredTarget,
  inputToStoredWeight,
  savedTargetSummary,
  storedTargetToInput,
  storedWeightToInput,
  targetDraftUnchanged,
} from './evaluationInputUnits';

function line(overrides: Partial<EvaluationLine> = {}): EvaluationLine {
  return {
    kpi_key: 'Attendance',
    label: 'Attendance',
    weight: 0.6,
    direction: 'higher_better',
    target: 0.65,
    target_mode: 'workbook',
    unit: '%',
    ...overrides,
  };
}

describe('evaluation input units', () => {
  it('shows a stored percent fraction as a percentage and stores a percentage as a fraction', () => {
    expect(storedTargetToInput(0.65, '%')).toBe('65');
    expect(inputToStoredTarget('70', '%')).toEqual({ ok: true, value: 0.7 });
    expect(inputToStoredTarget(' 70 ', 'percent')).toEqual({ ok: true, value: 0.7 });
    expect(storedTargetToInput(0.65, 'Percentage')).toBe('65');
    expect(storedTargetToInput(0.001, '%')).toBe('0.1');
    expect(inputToStoredTarget('0.1', '%')).toEqual({ ok: true, value: 0.001 });
    expect(inputToStoredTarget('0', '%')).toEqual({ ok: true, value: 0 });
    expect(storedTargetToInput(0, '%')).toBe('0');
  });

  it('shows every weight as a percent and stores the fraction without clamping', () => {
    expect(storedWeightToInput(0.6)).toBe('60');
    expect(inputToStoredWeight('50')).toEqual({ ok: true, value: 0.5 });
    expect(storedWeightToInput(0)).toBe('0');
    expect(inputToStoredWeight('0')).toEqual({ ok: true, value: 0 });
    expect(inputToStoredWeight('100')).toEqual({ ok: true, value: 1 });
    expect(inputToStoredWeight('110')).toEqual({ ok: true, value: 1.1 });
    expect(inputToStoredWeight('-5')).toEqual({ ok: true, value: -0.05 });
  });

  it('leaves hours, counts, and unknown units on the stored scale', () => {
    expect(storedTargetToInput(2.5, 'hours')).toBe('2.5');
    expect(inputToStoredTarget('2.5', 'hours')).toEqual({ ok: true, value: 2.5 });
    expect(storedTargetToInput(2.5, 'min')).toBe('2.5');
    const rework = line({ kpi_key: 'Rework', label: 'Rework percentage', unit: 'count', target: 65, weight: 0 });
    expect(storedTargetToInput(rework.target, rework.unit)).toBe('65');
    expect(inputToStoredTarget('65', 'count')).toEqual({ ok: true, value: 65 });
    expect(inputToStoredTarget('70', 'AED')).toEqual({ ok: true, value: 70 });
    expect(storedTargetToInput(65, 'boxes')).toBe('65');
    expect(storedTargetToInput(65, undefined)).toBe('65');
    expect(storedTargetToInput(65, '   ')).toBe('65');
    expect(inputToStoredTarget('65', undefined)).toEqual({ ok: true, value: 65 });
    expect(formatIdentifiedTarget(0.6, '%')).toBe('60%');
    expect(formatIdentifiedTarget(2.5, 'hours')).toBe('2.5 hours');
    expect(formatIdentifiedTarget(65, 'count')).toBe('65 count');
    expect(formatIdentifiedTarget(65, undefined)).toBe('65 (stored value, unit not provided)');
    expect(formatIdentifiedTarget(null, '%')).toBe('—');
  });

  it('rejects blank and non-finite text without turning it into zero', () => {
    for (const text of ['', '   ', '0.', '.', 'Infinity', '+Infinity', 'NaN', 'abc', '1e309', '1e2', '1,000', '--1']) {
      expect(inputToStoredTarget(text, '%').ok).toBe(false);
      expect(inputToStoredWeight(text).ok).toBe(false);
    }
    const stored = line();
    const blank = commitLineInputs([stored], { Attendance: { targetText: '' } });
    expect(blank.ok).toBe(false);
    if (!blank.ok) {
      expect(blank.errors[0]?.reason).toBe('blank');
      expect(blank.errors[0]?.message).toContain('Saved target remains 65%.');
      expect(blank.errors[0]?.message).not.toMatch(/NaN|Infinity|\b0%/);
    }
    const unfinished = commitLineInputs([stored], { Attendance: { targetText: '0.' } });
    expect(unfinished.ok).toBe(false);
    if (!unfinished.ok) {
      expect(unfinished.errors[0]?.reason).toBe('invalid');
      expect(unfinished.errors[0]?.message).toContain('Saved target remains 65%.');
    }
    const weightBlank = commitLineInputs([stored], { Attendance: { weightText: ' ' } });
    expect(weightBlank.ok).toBe(false);
    if (!weightBlank.ok) expect(weightBlank.errors[0]?.message).toContain('Saved weight remains 60%.');
    expect(savedTargetSummary(line({ target: null, unit: 'hours' }))).toBe('empty');
  });

  it('keeps untouched numbers and a missing workbook target exact across a mixed save', () => {
    const preciseWeight = 0.1 + 0.2;
    const preciseTarget = 1 / 3;
    const percent = line({ weight: preciseWeight, target: preciseTarget });
    const hours = line({ kpi_key: 'HandleTime', label: 'Handle time', unit: 'hours', target: 2.5, weight: 0, direction: 'lower_better', target_mode: 'fixed' });
    const count = line({ kpi_key: 'Calls', label: 'Calls', unit: 'count', target: 65, weight: 0.6, target_mode: 'fixed' });
    const unknown = line({ kpi_key: 'Mystery', label: 'Mystery', unit: undefined, target: 65, weight: 0, target_mode: 'fixed' });
    const workbook = line({ kpi_key: 'Quality', label: 'Quality', target: null, weight: 0.5, target_mode: 'workbook' });

    expect(targetDraftUnchanged(workbook, '')).toBe(true);
    expect(targetDraftUnchanged(workbook, '0')).toBe(false);
    const untouchedBlank = commitLineInputs([workbook], { Quality: { targetText: '' } });
    expect(untouchedBlank).toEqual({ ok: true, lines: [workbook] });

    const committed = commitLineInputs(
      [percent, hours, count, unknown, workbook],
      { Attendance: { targetText: '70' }, Calls: { weightText: '50' } },
    );
    expect(committed.ok).toBe(true);
    if (!committed.ok) return;
    expect(Object.is(committed.lines[0]?.target, 0.7)).toBe(true);
    expect(Object.is(committed.lines[0]?.weight, preciseWeight)).toBe(true);
    expect(committed.lines[0]?.target_mode).toBe('workbook');
    expect(committed.lines[1]).toBe(hours);
    expect(Object.is(committed.lines[1]?.target, 2.5)).toBe(true);
    expect(Object.is(committed.lines[2]?.target, 65)).toBe(true);
    expect(Object.is(committed.lines[2]?.weight, 0.5)).toBe(true);
    expect(committed.lines[3]).toBe(unknown);
    expect(Object.is(committed.lines[3]?.target, 65)).toBe(true);
    expect(committed.lines[4]).toBe(workbook);
    expect(committed.lines[4]?.target).toBeNull();

    const weightOnly = commitLineInputs([workbook], { Quality: { weightText: '40' } });
    expect(weightOnly.ok).toBe(true);
    if (!weightOnly.ok) return;
    expect(weightOnly.lines[0]?.target).toBeNull();
    expect(weightOnly.lines[0]?.target_mode).toBe('workbook');
    expect(weightOnly.lines[0]?.weight).toBe(0.4);
  });
});
