import { describe, expect, it } from 'vitest';
import type { AgentRecord } from '../../types';
import {
  buildMarketingAnalytics,
  buildMarketingInsights,
  getMarketingGrade,
  getMarketingPeriods,
} from './marketingAnalytics';
import type { MarketingTeamConfig } from './types';

const config: MarketingTeamConfig = {
  team: 'Marketing',
  db_name: 'Marketing',
  region: 'EGY',
  performance_level: 'Employee',
  grade_thresholds: { A: 95, B: 85, C: 75, D: 65 },
  available_positions: ['Media Buyer', 'Graphic Designer', 'Social Media Specialist', 'Web Developer', 'Content Writer'],
  positions: {
    'Media Buyer': {
      kpis: [
        { key: 'cpl', label: 'CPL', perspective: 'Financial', weight: 0.5, direction: 'lower_better', unit: 'AED', color: '#2563EB', display_order: 1 },
        { key: 'leads', label: 'Leads', perspective: 'Customer', weight: 0.5, direction: 'higher_better', unit: 'count', color: '#10B981', display_order: 2 },
      ],
    },
    'Graphic Designer': { kpis: [] },
    'Social Media Specialist': { kpis: [] },
    'Web Developer': { kpis: [] },
    'Content Writer': { kpis: [] },
  },
};

const record = ({
  id,
  year,
  month,
  position = 'Media Buyer',
  region = 'EGY',
  score,
  grade,
  status,
  cplAchievement = 0.8,
  cplActual = 125,
  cplTarget = 100,
  leadsAchievement = 1,
}: {
  id: string;
  year: number;
  month: string;
  position?: string;
  region?: string;
  score: number;
  grade: string;
  status?: string;
  cplAchievement?: number;
  cplActual?: number;
  cplTarget?: number;
  leadsAchievement?: number;
}): AgentRecord => ({
  year,
  position,
  region,
  status,
  performance_level: 'Employee',
  identity: { name: `Employee ${id}`, employee_id: id, team: 'Marketing', month, position, region },
  calls: { inbound: 0, outbound: 0, total_handled: 0, abandoned: 0, aht_raw: '00:00:00' },
  geo: {
    bookings: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
    attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
  },
  actual: { booking_rate: 0, attend_rate: 0, abandon_rate: 0 },
  achievement: { booking_ach: 0, attend_ach: 0 },
  evaluation: { score, grade },
  kpi_values: [
    { kpi_key: 'cpl', label: 'CPL', unit: 'AED', direction: 'lower_better', actual_value: cplActual, target_value: cplTarget, achievement_ratio: cplAchievement, weight_applied: 0.5, contribution: Math.min(cplAchievement, 1) * 0.5 },
    { kpi_key: 'leads', label: 'Leads', unit: 'count', direction: 'higher_better', actual_value: leadsAchievement * 100, target_value: 100, achievement_ratio: leadsAchievement, weight_applied: 0.5, contribution: Math.min(leadsAchievement, 1) * 0.5 },
  ],
});

describe('marketing analytics', () => {
  it('sorts periods by year and month without mixing equal month names', () => {
    const periods = getMarketingPeriods([
      record({ id: '1', year: 2026, month: 'June', score: 90, grade: 'B' }),
      record({ id: '2', year: 2025, month: 'June', score: 80, grade: 'C' }),
      record({ id: '3', year: 2026, month: 'May', score: 70, grade: 'D' }),
    ]);
    expect(periods.map((period) => period.label)).toEqual(['June 2025', 'May 2026', 'June 2026']);
  });

  it('uses the backend A-E grade before applying Marketing thresholds', () => {
    expect(getMarketingGrade(record({ id: '1', year: 2026, month: 'June', score: 86, grade: 'C' }), config.grade_thresholds)).toBe('C');
    expect(getMarketingGrade(record({ id: '2', year: 2026, month: 'June', score: 86, grade: 'Meet Expectations' }), config.grade_thresholds)).toBe('B');
  });

  it('separates positions, counts unique employees, and resolves previous period', () => {
    const records = [
      record({ id: '1', year: 2026, month: 'May', score: 80, grade: 'C' }),
      record({ id: '1', year: 2026, month: 'June', score: 90, grade: 'B' }),
      record({ id: '2', year: 2026, month: 'June', score: 70, grade: 'D' }),
      record({ id: '3', year: 2026, month: 'June', position: 'Graphic Designer', score: 95, grade: 'A' }),
    ];
    const analytics = buildMarketingAnalytics(records, config, {
      year: 2026,
      month: 'June',
      region: 'All',
    });
    expect(analytics.employeeCount).toBe(3);
    expect(analytics.positionsWithData).toBe(2);
    expect(analytics.previousPeriod?.label).toBe('May 2026');
    expect(analytics.scoreDelta).toBeCloseTo(6.25);
    expect(analytics.employeeRows.find((employee) => employee.id === '1')?.scoreDelta).toBeCloseTo(12.5);
    expect(analytics.positionSummaries.find((item) => item.position === 'Media Buyer')?.employeeCount).toBe(2);
    expect(analytics.positionSummaries.find((item) => item.position === 'Content Writer')?.dataStatus).toBe('No Uploaded Data');
  });

  it('averages all selected-year months while keeping one row per employee', () => {
    const analytics = buildMarketingAnalytics([
      record({ id: '1', year: 2026, month: 'May', score: 60, grade: 'E' }),
      record({ id: '1', year: 2026, month: 'June', score: 80, grade: 'B' }),
      record({ id: '2', year: 2026, month: 'May', score: 90, grade: 'A' }),
      record({ id: '2', year: 2026, month: 'June', score: 70, grade: 'D' }),
    ], config, {
      year: 2026,
      month: 'All',
      region: 'All',
    });

    expect(analytics.currentRecords).toHaveLength(4);
    expect(analytics.employeeCount).toBe(2);
    expect(analytics.employeeRows).toHaveLength(2);
    expect(analytics.averageScore).toBe(75);
    expect(analytics.employeeRows.map((employee) => employee.score).sort()).toEqual([70, 80]);
    expect(analytics.employeeRows.every((employee) => employee.scoreDelta === null)).toBe(true);
    expect(analytics.previousPeriod).toBeNull();
    expect(analytics.scoreDelta).toBeNull();
    expect(analytics.positionSummaries.find((item) => item.position === 'Media Buyer')?.averageScore).toBe(75);
    expect(analytics.trend.map((point) => point.month)).toEqual(['May', 'June']);
  });

  it('averages KPI values and uses direction when calculating focus gaps', () => {
    const records = [
      record({ id: '1', year: 2026, month: 'May', score: 75, grade: 'C', cplActual: 100, cplTarget: 100, cplAchievement: 1, leadsAchievement: 0.4 }),
      record({ id: '1', year: 2026, month: 'June', score: 80, grade: 'C', cplActual: 125, cplTarget: 100, cplAchievement: 0.8, leadsAchievement: 0.5 }),
      record({ id: '2', year: 2026, month: 'June', score: 90, grade: 'B', cplActual: 100, cplTarget: 100, cplAchievement: 1, leadsAchievement: 1 }),
    ];
    const analytics = buildMarketingAnalytics(records, config, {
      year: 2026,
      month: 'June',
      region: 'All',
      position: 'Media Buyer',
    });
    const cpl = analytics.kpiAggregates.find((item) => item.key === 'cpl');
    const leads = analytics.kpiAggregates.find((item) => item.key === 'leads');
    expect(cpl?.averageActual).toBe(112.5);
    expect(cpl?.previousActual).toBe(100);
    expect(cpl?.previousTarget).toBe(100);
    expect(cpl?.averageAchievement).toBe(90);
    expect(cpl?.averageGap).toBe(25);
    expect(cpl?.currentPeriodLabel).toBe('June 2026');
    expect(cpl?.previousPeriodLabel).toBe('May 2026');
    expect(cpl?.baselineActual).toBe(100);
    expect(cpl?.baselinePeriodLabel).toBe('May 2026');
    expect(cpl?.isNewBaseline).toBe(false);
    expect(leads?.averageGap).toBe(50);
    expect(analytics.employeeRows[1].weakestKpi?.key).toBe('leads');
  });

  it('uses only the selected position history up to the selected month for baseline and previous comparison', () => {
    const analytics = buildMarketingAnalytics([
      record({ id: '1', year: 2026, month: 'April', score: 75, grade: 'C', cplActual: 110 }),
      record({ id: '1', year: 2026, month: 'May', score: 80, grade: 'C', cplActual: 100 }),
      record({ id: '1', year: 2026, month: 'June', score: 90, grade: 'B', cplActual: 90 }),
      record({ id: '1', year: 2026, month: 'July', score: 95, grade: 'A', cplActual: 70 }),
      record({ id: 'design', year: 2026, month: 'May', position: 'Graphic Designer', score: 99, grade: 'A', cplActual: 1 }),
    ], config, {
      year: 2026,
      month: 'June',
      region: 'All',
      position: 'Media Buyer',
    });

    const cpl = analytics.kpiAggregates.find((item) => item.key === 'cpl');
    expect(analytics.previousPeriod?.label).toBe('May 2026');
    expect(cpl?.previousActual).toBe(100);
    expect(cpl?.baselineActual).toBe(90);
    expect(cpl?.baselinePeriodLabel).toBe('June 2026');
    expect(cpl?.previousBaselineActual).toBe(100);
    expect(cpl?.previousBaselinePeriodLabel).toBe('May 2026');
    expect(cpl?.isNewBaseline).toBe(true);
  });

  it('applies the Position filter to every overview analytics collection', () => {
    const analytics = buildMarketingAnalytics([
      record({ id: '1', year: 2026, month: 'June', score: 80, grade: 'C' }),
      record({ id: '2', year: 2026, month: 'June', position: 'Graphic Designer', score: 95, grade: 'A' }),
    ], config, {
      year: 2026,
      month: 'June',
      region: 'All',
      position: 'Graphic Designer',
    });

    expect(analytics.currentRecords).toHaveLength(1);
    expect(analytics.currentRecords[0].position).toBe('Graphic Designer');
    expect(analytics.employeeCount).toBe(1);
    expect(analytics.positionsWithData).toBe(1);
    expect(analytics.trend.every((point) => point.employeeCount === 1)).toBe(true);
  });

  it('keeps target zero and actual zero as zero achievement and contribution', () => {
    const zero = record({
      id: '1',
      year: 2026,
      month: 'June',
      score: 50,
      grade: 'E',
      cplActual: 0,
      cplTarget: 0,
      cplAchievement: 0,
    });
    const analytics = buildMarketingAnalytics([zero], config, {
      year: 2026,
      month: 'June',
      region: 'All',
      position: 'Media Buyer',
    });
    const cpl = analytics.kpiAggregates.find((item) => item.key === 'cpl');
    expect(cpl?.averageAchievement).toBe(0);
    expect(cpl?.averageContribution).toBe(0);
  });

  it('selects the last six periods that still have results after filters', () => {
    const records = [
      ...['January', 'February', 'March', 'April', 'May', 'June'].map((month, index) => (
        record({ id: `media-${index}`, year: 2026, month, score: 80 + index, grade: 'C' })
      )),
      record({ id: 'design-1', year: 2026, month: 'July', position: 'Graphic Designer', score: 90, grade: 'B' }),
      record({ id: 'design-2', year: 2026, month: 'August', position: 'Graphic Designer', score: 95, grade: 'A' }),
    ];
    const analytics = buildMarketingAnalytics(records, config, {
      year: 2026,
      month: 'June',
      region: 'All',
      position: 'Media Buyer',
    });

    expect(analytics.trend.map((point) => point.month)).toEqual([
      'January', 'February', 'March', 'April', 'May', 'June',
    ]);
  });

  it('builds overview insights from the selected analytics instead of fixed values', () => {
    const analytics = buildMarketingAnalytics([
      record({ id: '1', year: 2026, month: 'May', score: 90, grade: 'B' }),
      record({ id: '1', year: 2026, month: 'June', score: 70, grade: 'D' }),
      record({ id: '2', year: 2026, month: 'June', position: 'Graphic Designer', score: 95, grade: 'A' }),
    ], config, {
      year: 2026,
      month: 'June',
      region: 'All',
    });

    const insights = buildMarketingInsights(analytics, config.grade_thresholds);
    expect(insights[0].title).toContain('Media Buyer');
    expect(insights[0].detail).toContain('22.2% MoM');
    expect(insights.some((insight) => insight.title.includes('Graphic Designer'))).toBe(true);
  });
});
