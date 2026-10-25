import { describe, expect, it } from 'vitest';
import type { ExecutiveSummary } from '../executive/types';
import { adaptSummaryToMonthlyOverview } from './monthlyOverviewData';

/** The fields the overview adapter reads. Compose stores grades as counts, not a `.grades` list. */
function liveSummary(gradeDistribution: ExecutiveSummary['grade_distribution']): ExecutiveSummary {
  return {
    data_status: { has_data: true, last_upload: null },
    hero: {
      label: 'UAE',
      score: 91.8,
      previous_score: 89.9,
      change: 1.9,
      gap: -8.2,
      target: 100,
      grade: 'B',
      employees: 4,
      teams_count: 2,
      functions_count: 1,
      story: null,
      comparison: null,
    },
    period: {
      requested: null,
      effective: { key: '2026-09', month: 'September', year: 2026, label: 'September 2026' },
      previous: { key: '2026-08', month: 'August', year: 2026, label: 'August 2026' },
      fallback_applied: false,
      notice: null,
    },
    trend: [],
    drivers: { negative: [], positive: [] },
    functions: [],
    teams: [],
    grade_distribution: gradeDistribution,
  } as ExecutiveSummary;
}

describe('adaptSummaryToMonthlyOverview', () => {
  it('maps compose grade counts for a live UAE month instead of calling .grades.find', () => {
    const overview = adaptSummaryToMonthlyOverview(
      liveSummary({
        total: 4,
        counts: { A: 1, B: 2, C: 1, D: 0, E: 0 },
        percents: { A: 25, B: 50, C: 25, D: 0, E: 0 },
        previous_counts: { A: 0, B: 2, C: 2, D: 0, E: 0 },
        movement: { A: 1, B: 0, C: -1, D: 0, E: 0 },
      }),
      'UAE',
    );

    expect(overview.regionName).toBe('UAE Region');
    expect(overview.overall.score).toBe(91.8);
    expect(overview.gradeDistribution.totalEmployees).toBe(4);
    expect(overview.gradeDistribution.rows.find((row) => row.grade === 'B')).toMatchObject({
      label: 'Meet Expectations',
      count: 2,
      percentage: 50,
      change: 0,
    });
    expect(overview.gradeDistribution.rows.find((row) => row.grade === 'A')).toMatchObject({
      count: 1,
      percentage: 25,
      change: 1,
    });
  });

  it('keeps the region snapshot when a live summary has no grade distribution', () => {
    const overview = adaptSummaryToMonthlyOverview(liveSummary(null), 'UAE');

    expect(overview.regionName).toBe('UAE Region');
    expect(overview.overall.score).toBe(91.8);
    expect(overview.gradeDistribution.rows.find((row) => row.grade === 'B')?.count).toBe(25);
  });

  it('does not refill a live UAE month with Egypt drivers, risk teams, or the Egypt grade story', () => {
    const overview = adaptSummaryToMonthlyOverview(
      liveSummary({
        total: 4,
        counts: { A: 1, B: 1, C: 2, D: 0, E: 0 },
        percents: { A: 25, B: 25, C: 50, D: 0, E: 0 },
        previous_counts: null,
        movement: null,
      }),
      'UAE',
    );

    const leaked = JSON.stringify({
      drivers: overview.drivers,
      teamsAtRisk: overview.teamsAtRisk,
      takeaway: overview.gradeDistribution.takeaway,
    });
    expect(leaked).not.toMatch(/Coding EGY|Submission EGY|tiny high-performing/);
    expect(overview.drivers.negative).toEqual([]);
    expect(overview.drivers.positive).toEqual([]);
    expect(overview.teamsAtRisk).toEqual([]);
  });
});
