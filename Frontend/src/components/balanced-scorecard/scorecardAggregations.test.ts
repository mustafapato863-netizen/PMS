import { describe, expect, it } from 'vitest';
import { averageScoreForYear } from './scorecardAggregations';

describe('averageScoreForYear', () => {
  it('averages all measured months in the selected year', () => {
    expect(averageScoreForYear([
      { year: 2026, score: 60 },
      { year: 2026, score: 70 },
      { year: 2026, score: 80 },
    ], 2026)).toBe(70);
  });

  it('ignores other years, missing scores, and non-finite scores', () => {
    expect(averageScoreForYear([
      { year: 2025, score: 10 },
      { year: 2026, score: 80 },
      { year: 2026, score: null },
      { year: 2026, score: Number.NaN },
    ], '2026')).toBe(80);
  });

  it('returns null when the year has no measured scores', () => {
    expect(averageScoreForYear([{ year: 2025, score: 90 }], 2026)).toBeNull();
  });
});
