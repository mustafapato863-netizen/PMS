import { describe, expect, it } from 'vitest';
import { toExecRecords } from '../features/executive/compose';
import { mapScopedPerformanceRecord, normalizeScore, resolveRecordGradeClass } from '../hooks/usePerformanceData';
import type { AgentRecord } from '../types';
import { normalizePerformanceScore, resolveDisplayScore } from './kpiScore';

describe('score scale rule', () => {
  it('treats a value in (0, 1] as a ratio and a value above 1 as a percentage', () => {
    expect(normalizePerformanceScore(0.85)).toBeCloseTo(85);
    expect(normalizePerformanceScore(1)).toBe(100);
    expect(normalizePerformanceScore(0.5)).toBeCloseTo(50);
    expect(normalizePerformanceScore(5.48)).toBeCloseTo(5.48);
    expect(normalizePerformanceScore(10)).toBe(10);
    expect(normalizePerformanceScore(0)).toBe(0);
  });

  it('returns a percentage-form score (Offshore-style) unchanged', () => {
    expect(normalizePerformanceScore(51.28)).toBeCloseTo(51.28);
    expect(normalizeScore(51.28)).toBeCloseTo(51.28);
  });

  it.each([0, 0.5])('keeps a published score of %s percentage points across report views', (score) => {
    const record = mapScopedPerformanceRecord({
      employee_id: 'CSR-1', employee_name: 'Test CSR', team: 'CSR', month: 'October', year: 2026,
      score, grade: 'D', raw_data: { ScoringMethod: 'uae_published_employee_score' },
    });
    expect(resolveDisplayScore(record, undefined)).toBe(score);
    expect(resolveRecordGradeClass(record)).toBe('D');
    expect(toExecRecords([record]).map((item) => item.score)).toEqual([score]);
  });

  it('grades a score with 95 / 90 / 80 / 70 for every team', () => {
    const graded = (score: number, stored: string) => resolveRecordGradeClass(
      { evaluation: { score, grade: stored } } as AgentRecord,
    );
    expect(graded(86, 'B')).toBe('C');
    expect(graded(92, 'C')).toBe('B');
    expect(graded(70, 'E')).toBe('D');
    expect(graded(69.9, 'D')).toBe('E');
    expect(graded(0, 'A')).toBe('A');
  });
});
