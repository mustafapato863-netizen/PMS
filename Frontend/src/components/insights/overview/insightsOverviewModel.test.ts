import { describe, expect, it } from 'vitest';
import type { InsightDriver, InsightKpiTrend, InsightPeopleContributionAnalysis } from '../../../features/insights/types';
import {
  achievementPercent,
  barShare,
  buildPerformanceTrend,
  formatSignedPercent,
  geographyGap,
  lowPerformingTeams,
  peopleToReview,
  sparklinePoints,
  splitDrivers,
  teamGap,
  teamsNeedingAttention,
  type TeamSummary,
} from './insightsOverviewModel';

const team = (name: string, current: number | null, extra: Partial<TeamSummary> = {}): TeamSummary => ({
  team: name, current_score: current, previous_score: null, score_change: null,
  impacted_employees: 0, total_employees: 1, critical: 0, at_risk: 0, opportunities: 0,
  main_insight_id: null, main_cause: null, ...extra,
});

const driver = (id: string, impact: number): InsightDriver => ({
  id, driver: id, scope: 'Team · Role', impact_points: impact,
  direction: impact < 0 ? 'negative' : 'positive', insight_id: `${id}-insight`,
});

describe('insightsOverviewModel', () => {
  it('computes direction-aware achievement and refuses to guess', () => {
    expect(achievementPercent(84, 100, 'higher_better')).toBeCloseTo(84);
    expect(achievementPercent(136, 60, 'lower_better')).toBeCloseTo(44.12, 1);
    expect(achievementPercent(0, 60, 'lower_better')).toBe(100);
    expect(achievementPercent(120, 100, 'higher_better')).toBeCloseTo(120);
    expect(achievementPercent(null, 100, 'higher_better')).toBeNull();
    expect(achievementPercent(50, 0, 'higher_better')).toBeNull();
    expect(achievementPercent(50, 100, null)).toBeNull();
  });

  it('normalises the leading KPI trend to % of target and keeps missing months empty', () => {
    const trend: InsightKpiTrend = {
      kpi_key: 'rate', kpi_label: 'Rate', unit: '%', direction: 'higher_better',
      points: [
        { period: { year: 2026, month: 'May', key: '2026-05' }, actual_value: null, target_value: null, measured_records: 0 },
        { period: { year: 2026, month: 'June', key: '2026-06' }, actual_value: 0.6, target_value: 0.8, measured_records: 4 },
      ],
    };
    const points = buildPerformanceTrend(trend);
    expect(points[0]).toEqual({ label: 'May', key: '2026-05', actual: null, target: null });
    expect(points[1]).toMatchObject({ label: 'Jun', key: '2026-06', target: 100 });
    expect(points[1].actual).toBeCloseTo(75);
    expect(buildPerformanceTrend(null)).toEqual([]);
  });

  it('splits and ranks drivers, with bars relative to the largest visible driver', () => {
    const split = splitDrivers([driver('a', -2), driver('b', 6), driver('c', -8), driver('d', 1), driver('e', -1), driver('f', -4)]);
    expect(split.negative.map((item) => item.id)).toEqual(['c', 'f', 'a']);
    expect(split.positive.map((item) => item.id)).toEqual(['b', 'd']);
    expect(split.maxMagnitude).toBe(8);
    expect(barShare(-4, 8)).toBe(50);
    expect(barShare(3, 0)).toBe(0);
  });

  it('derives team and geography gaps from the API, falling back to score - 100', () => {
    expect(teamGap(team('A', 70, { gap_points: -31 }))).toBe(-31);
    expect(teamGap(team('B', 69.9))).toBe(-30.1);
    expect(teamGap(team('C', null))).toBeNull();
    expect(geographyGap({
      scope: 'UAE', current_score: 74.6, previous_score: null, score_change: null, gap_points: null,
      gap_contribution_percent: 82.7, impacted_employees: 0, total_employees: 1, affected_percentage: null,
    })).toBe(-25.4);
  });

  it('keeps API team order for attention and selects D/E teams as low performers', () => {
    const teams = [team('CSR', 55.6), team('Inbound', 90.3), team('Coding', 66.5), team('Pharmacy', 86.8), team('Marketing', 77.4), team('Empty', null)];
    expect(teamsNeedingAttention(teams, 5).map((item) => item.team)).toEqual(['CSR', 'Inbound', 'Coding', 'Pharmacy', 'Marketing']);
    expect(lowPerformingTeams(teams).map((item) => item.team)).toEqual(['CSR', 'Coding', 'Marketing']);
  });

  it('returns the negative contributors with KPI achievement for grading', () => {
    const analysis: InsightPeopleContributionAnalysis = {
      kpi_key: 'k', kpi_label: 'K', unit: '%', direction: 'higher_better',
      total_employees: 3, negative_contributors: 2, positive_contributors: 1, data_issues: 0,
      rows: [
        { employee_id: '1', employee_name: 'Small', team: 'T', performance_level: 'Employee', position: 'P', kpi_key: 'k', kpi_label: 'K', unit: '%', direction: 'higher_better', current_value: 84, target_value: 100, gap: -16, weighted_impact: -3.2, trend: null, severity: 'Medium', classification: 'negative' },
        { employee_id: '2', employee_name: 'Large', team: 'T', performance_level: 'Employee', position: 'P', kpi_key: 'k', kpi_label: 'K', unit: '%', direction: 'higher_better', current_value: 55.6, target_value: 100, gap: -44.4, weighted_impact: -5.9, trend: null, severity: 'High', classification: 'negative' },
        { employee_id: '3', employee_name: 'Helper', team: 'T', performance_level: 'Employee', position: 'P', kpi_key: 'k', kpi_label: 'K', unit: '%', direction: 'higher_better', current_value: 120, target_value: 100, gap: 20, weighted_impact: 1.2, trend: null, severity: 'Low', classification: 'positive' },
      ],
    };
    const people = peopleToReview(analysis);
    expect(people.map((person) => person.employee_name)).toEqual(['Large', 'Small']);
    expect(people[0].achievement).toBeCloseTo(55.6);
    expect(peopleToReview(null)).toEqual([]);
  });

  it('maps sparkline values into the 72×26 Figma box and needs two measurements', () => {
    expect(sparklinePoints([90, 69.9])).toEqual([{ x: 4, y: 6 }, { x: 68, y: 18 }]);
    expect(sparklinePoints([80, 80])).toEqual([{ x: 4, y: 12 }, { x: 68, y: 12 }]);
    expect(sparklinePoints([null, 70])).toEqual([]);
  });

  it('formats signed percentages and missing values', () => {
    expect(formatSignedPercent(2.44)).toBe('+2.4%');
    expect(formatSignedPercent(-22.5)).toBe('-22.5%');
    expect(formatSignedPercent(null)).toBe('N/A');
  });
});
