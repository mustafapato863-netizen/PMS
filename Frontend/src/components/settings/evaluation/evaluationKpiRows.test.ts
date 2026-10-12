import { describe, expect, it } from 'vitest';
import type { EvaluationLine } from '../evaluationSettings';
import { distinctTargetHelp, fieldKeyFor, isRowEdited } from './evaluationKpiRows';

const SAVED: EvaluationLine = {
  kpi_key: 'QualityErrors',
  label: 'Quality errors',
  weight: 0.1,
  direction: 'higher_better',
  target: 0.55,
  target_mode: 'workbook',
  unit: '%',
};

describe('isRowEdited', () => {
  it('is not edited when the row matches the saved line and has no draft', () => {
    expect(isRowEdited(SAVED, SAVED, undefined)).toBe(false);
  });

  it('is not edited when the draft text is the saved value written another way', () => {
    // 55 is the stored 0.55 shown on a percent scale, so the same value is unchanged.
    expect(isRowEdited(SAVED, SAVED, { targetText: '55' })).toBe(false);
    expect(isRowEdited(SAVED, SAVED, { weightText: '10' })).toBe(false);
  });

  it('is edited when the target text changes to a different value', () => {
    expect(isRowEdited(SAVED, SAVED, { targetText: '56' })).toBe(true);
  });

  it('is edited when the target text is cleared', () => {
    expect(isRowEdited(SAVED, SAVED, { targetText: '' })).toBe(true);
  });

  it('is edited when the weight text changes to a different value', () => {
    expect(isRowEdited(SAVED, SAVED, { weightText: '11' })).toBe(true);
  });

  it('is edited when the direction differs from the saved direction', () => {
    expect(isRowEdited({ ...SAVED, direction: 'lower_better' }, SAVED, undefined)).toBe(true);
  });

  it('is edited when the source differs from the saved source', () => {
    expect(isRowEdited({ ...SAVED, target_mode: 'fixed' }, SAVED, undefined)).toBe(true);
  });

  it('is never edited when there is no saved line to compare with', () => {
    expect(isRowEdited({ ...SAVED, direction: 'lower_better' }, undefined, { targetText: '99' })).toBe(false);
  });
});

describe('distinctTargetHelp', () => {
  it('returns each unit instruction once, in first-use order', () => {
    expect(distinctTargetHelp(['%', '%', undefined, 'hours', '%'])).toEqual([
      'Enter a percentage. 65 is stored as 0.65.',
      'No unit was provided. The value is stored as entered.',
      'Enter hours. The value is stored as entered.',
    ]);
  });

  it('returns nothing for no rows', () => {
    expect(distinctTargetHelp([])).toEqual([]);
  });
});

describe('fieldKeyFor', () => {
  it('turns a KPI key into an id-safe fragment', () => {
    expect(fieldKeyFor('Quality errors (QA)')).toBe('Quality-errors--QA-');
    expect(fieldKeyFor('AHT_2')).toBe('AHT_2');
  });
});
