import { describe, expect, it } from 'vitest';
import { getGaugeTone } from './gaugeTone';
import { fmtScore, scoreClass, scoreLabel, statusClass, statusLabel } from './types';

describe('getGaugeTone (Overall Performance / gauges)', () => {
  it('paints 70.3% as D Below Average orange, not green "Good"', () => {
    const tone = getGaugeTone(70.3);
    expect(tone).toMatchObject({
      grade: 'D',
      label: 'Below Average',
      color: 'var(--pms-grade-d-gauge)',
      text: 'var(--pms-grade-d-text)',
      glow: 'var(--pms-grade-d-glow)',
      background: 'var(--pms-grade-d-badge-bg)',
      badgeText: 'var(--pms-grade-d-badge-text)',
      border: 'var(--pms-grade-d-border)',
    });
  });

  it.each([
    [97.2, 'A', 'Excellent'],
    [95, 'A', 'Excellent'],
    [92, 'B', 'Meet Expectations'],
    [84, 'C', 'Average'],
    [70, 'D', 'Below Average'],
    [69.9, 'E', 'Unsatisfactory'],
    [41, 'E', 'Unsatisfactory'],
  ] as const)('maps %s → grade %s (%s)', (score, grade, label) => {
    const tone = getGaugeTone(score);
    expect(tone.grade).toBe(grade);
    expect(tone.label).toBe(label);
    expect(tone.color).toBe(`var(--pms-grade-${grade.toLowerCase()}-gauge)`);
  });

  it('keeps the No data state for missing scores', () => {
    for (const score of [null, undefined, Number.NaN]) {
      const tone = getGaugeTone(score);
      expect(tone.grade).toBeNull();
      expect(tone.label).toBe('No data');
      expect(tone.color).toBe('var(--pms-grade-na-gauge)');
    }
  });

  it('no longer emits the retired Excellent/Good/Needs attention/Poor scheme', () => {
    const labels = [100, 90, 89, 75, 70, 60, 50, 49, 0].map((s) => getGaugeTone(s).label);
    expect(labels).not.toContain('Good');
    expect(labels).not.toContain('Needs attention');
    expect(labels).not.toContain('Poor');
    expect(labels.join(' ')).not.toMatch(/#1A9E72|#1A8C53/);
  });
});

describe('BSC scoreClass / status helpers', () => {
  it.each([
    [95, 'grade-a'],
    [90, 'grade-b'],
    [80, 'grade-c'],
    [75, 'grade-d'],
    [70.3, 'grade-d'],
    [69.99, 'grade-e'],
    [null, 'na'],
    [undefined, 'na'],
  ] as const)('scoreClass(%s) → %s', (score, tone) => {
    expect(scoreClass(score)).toBe(tone);
  });

  it('labels scores with the employee grade scale', () => {
    expect(scoreLabel(96)).toBe('Excellent');
    expect(scoreLabel(70.3)).toBe('Below Average');
    expect(scoreLabel(null)).toBe('N/A');
  });

  it('passes grade tones through StatusPill helpers', () => {
    expect(statusClass('grade-d')).toBe('grade-d');
    expect(statusLabel('grade-d')).toBe('Below Average');
    expect(statusLabel('grade-a')).toBe('Excellent');
  });

  it('does not color free-text legacy statuses as score grades', () => {
    expect(statusClass('Good')).toBe('na');
    expect(statusClass('Excellent')).toBe('na');
    expect(statusClass('Needs Attention')).toBe('na');
    expect(statusLabel('not_configured')).toBe('Not Configured');
    expect(statusLabel('No Data')).toBe('No Data');
  });

  it('still formats scores unchanged', () => {
    expect(fmtScore(70.3)).toBe('70.3%');
  });
});
