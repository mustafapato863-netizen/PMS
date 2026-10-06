import { describe, expect, it } from 'vitest';
import type { InsightDriver, InsightExecutiveStory, InsightKpiTrend, InsightPeopleContributionAnalysis } from '../../../features/insights/types';
import {
  achievementPercent,
  barShare,
  buildPerformanceTrend,
  movementTone,
  resolveAchievement,
  resolveKpiStatus,
  resolveMovementTone,
  selectTrendSeries,
  formatSignedPercent,
  geographyGap,
  lowPerformingTeams,
  peopleToReview,
  priorityFocusText,
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
    expect(points[0]).toMatchObject({ label: 'May', key: '2026-05', actual: null, target: null });
    expect(points[1].raw).toEqual({ actual: 0.6, target: 0.8, previous: null, unit: '%', direction: 'higher_better', trendStatus: null, changeValue: null, status: null });
    expect(points[1]).toMatchObject({ label: 'Jun', key: '2026-06', target: 100 });
    expect(points[1].actual).toBeCloseTo(75);
    expect(buildPerformanceTrend(null)).toEqual([]);
  });

  it('colours movement by KPI direction and stays neutral when flat or unknown', () => {
    expect(movementTone(5, 'higher_better')).toBe('good');
    expect(movementTone(-5, 'higher_better')).toBe('bad');
    // Lower-is-better (e.g. Rejection Rate): an increase is bad, a decrease is good.
    expect(movementTone(5, 'lower_better')).toBe('bad');
    expect(movementTone(-5, 'lower_better')).toBe('good');
    expect(movementTone(0, 'lower_better')).toBe('flat');
    expect(movementTone(3, null)).toBe('unknown');
    expect(movementTone(null, 'higher_better')).toBe('unknown');
  });

  it('prefers the overall score series and only falls back to the leading KPI without one', () => {
    const kpi: InsightKpiTrend = {
      kpi_key: 'rej', kpi_label: 'Rejection Rate', unit: '%', direction: 'lower_better',
      points: [{ period: { year: 2026, month: 'June', key: '2026-06' }, actual_value: 0.1, target_value: 0.05, measured_records: 3 }],
    };
    const overall = [
      { period: { year: 2026, month: 'May', key: '2026-05' }, score: 79.4, target: 100, measured_records: 5 },
      { period: { year: 2026, month: 'June', key: '2026-06' }, score: 77.5, target: 100, measured_records: 5 },
    ];
    const series = selectTrendSeries(overall, kpi);
    expect(series.source).toBe('overall');
    expect(series.direction).toBe('higher_better');
    expect(series.points.map((point) => point.actual)).toEqual([79.4, 77.5]);
    // An empty overall series means "no data", never a silent switch to the KPI.
    expect(selectTrendSeries([], kpi)).toMatchObject({ source: 'overall', points: [] });
    const fallback = selectTrendSeries(undefined, kpi);
    expect(fallback).toMatchObject({ source: 'kpi', kpiLabel: 'Rejection Rate', direction: 'lower_better' });
    // Lower-better: 5% target / 10% actual = 50% of target.
    expect(fallback.points[0].actual).toBeCloseTo(50);
  });

  it('prefers the API achievement_percent (PR #15) and falls back to the local rule', () => {
    // Present: the capped API value wins over the uncapped local value.
    expect(resolveAchievement(100, 0.04, 0.05, 'lower_better')).toBe(100);
    expect(resolveAchievement(62.5, 0.5, 0.8, 'higher_better')).toBe(62.5);
    // Absent: local direction-aware rule.
    expect(resolveAchievement(undefined, 0.04, 0.05, 'lower_better')).toBeCloseTo(125);
    expect(resolveAchievement(null, 0.5, 0.8, 'higher_better')).toBeCloseTo(62.5);
    expect(resolveAchievement(undefined, 0.5, 0.8, null)).toBeNull();
  });

  it('resolves the per-point KPI status from the API, else with the 100% / 70% thresholds', () => {
    expect(resolveKpiStatus('critical', 120)).toBe('critical');
    expect(resolveKpiStatus(undefined, 100)).toBe('on_track');
    expect(resolveKpiStatus(null, 70)).toBe('at_risk');
    expect(resolveKpiStatus(undefined, 69.9)).toBe('critical');
    expect(resolveKpiStatus(undefined, null)).toBeNull();
  });

  it('resolves movement tone from trend_status, then change_value, then raw delta + direction', () => {
    expect(resolveMovementTone({ trendStatus: 'improving', rawDelta: 5, direction: 'lower_better' })).toBe('good');
    expect(resolveMovementTone({ trendStatus: 'declining', rawDelta: -5, direction: 'higher_better' })).toBe('bad');
    expect(resolveMovementTone({ trendStatus: 'stable', rawDelta: 1 })).toBe('flat');
    expect(resolveMovementTone({ changeValue: -0.03, rawDelta: 0.03, direction: null })).toBe('bad');
    expect(resolveMovementTone({ changeValue: 0.03 })).toBe('good');
    // Absent fields: local direction-aware fallback.
    expect(resolveMovementTone({ rawDelta: 0.03, direction: 'lower_better' })).toBe('bad');
    expect(resolveMovementTone({ rawDelta: 0.03, direction: 'higher_better' })).toBe('good');
    expect(resolveMovementTone({ rawDelta: 0.03, direction: null })).toBe('unknown');
  });

  it('uses the API achievement_percent for the trend and people to review when present', () => {
    const trend: InsightKpiTrend = {
      kpi_key: 'rej', kpi_label: 'Rejection Rate', unit: '%', direction: 'lower_better',
      points: [
        { period: { year: 2026, month: 'May', key: '2026-05' }, actual_value: 0.04, target_value: 0.05, measured_records: 2, achievement_percent: 100, status: 'on_track', trend_status: null, change_value: null },
        { period: { year: 2026, month: 'June', key: '2026-06' }, actual_value: 0.04, target_value: 0.05, measured_records: 2 },
      ],
    };
    const points = buildPerformanceTrend(trend);
    expect(points[0].actual).toBe(100);
    expect(points[0].raw).toMatchObject({ status: 'on_track', trendStatus: null });
    expect(points[1].actual).toBeCloseTo(125);

    const analysis: InsightPeopleContributionAnalysis = {
      kpi_key: 'rej', kpi_label: 'Rejection Rate', unit: '%', direction: 'lower_better',
      total_employees: 2, negative_contributors: 2, positive_contributors: 0, data_issues: 0,
      rows: [
        { employee_id: 'a', employee_name: 'A', team: 'RCM', performance_level: 'Employee', position: 'Agent', kpi_key: 'rej', kpi_label: 'Rejection Rate', unit: '%', direction: 'lower_better', current_value: 0.1, target_value: 0.05, gap: -0.05, weighted_impact: -2, trend: 0.02, severity: 'High', classification: 'negative', achievement_percent: 50 },
        { employee_id: 'b', employee_name: 'B', team: 'RCM', performance_level: 'Employee', position: 'Agent', kpi_key: 'rej', kpi_label: 'Rejection Rate', unit: '%', direction: 'higher_better', current_value: 0.4, target_value: 0.8, gap: -0.4, weighted_impact: -1, trend: 0.01, severity: 'High', classification: 'negative' },
      ],
    };
    const people = peopleToReview(analysis);
    expect(people[0].achievement).toBe(50);
    expect(people[1].achievement).toBeCloseTo(50);
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

describe('priorityFocusText', () => {
  const story = (extra: Partial<InsightExecutiveStory>): InsightExecutiveStory => ({
    headline: '', scope_label: '', current_score: 77.5, target_score: 100, gap_points: -22.5, score_change: -1.9,
    primary_scope: null, primary_scope_contribution_percent: null, primary_driver: null, primary_driver_impact: null,
    recommended_focus: 'Review the highest-impact team and KPI drivers first.', confidence: 'high', evidence: [], ...extra,
  });

  it('names the primary weighted driver like Figma 29:2', () => {
    expect(priorityFocusText(story({ primary_driver: 'Case Management Referral Value (AED)' })))
      .toBe('Review Case Management Referral Value (AED) first — largest weighted gap.');
  });

  it('falls back to the API recommendation, then to a coverage prompt', () => {
    expect(priorityFocusText(story({}))).toBe('Review the highest-impact team and KPI drivers first.');
    expect(priorityFocusText(null)).toBe('Review data coverage before making a performance decision.');
  });
});
