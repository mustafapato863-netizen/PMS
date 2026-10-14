import { describe, expect, it } from 'vitest';
import type { InsightPeopleContributionAnalysis } from '../../../features/insights/types';
import {
  peopleToReview,
  resolveAchievement,
  resolveKpiStatus,
  resolveMovementTone,
} from './insightsOverviewModel';

describe('insightsOverviewModel', () => {
  it('computes direction-aware achievement and refuses to guess', () => {
    expect(resolveAchievement(undefined, 84, 100, 'higher_better')).toBeCloseTo(84);
    expect(resolveAchievement(undefined, 136, 60, 'lower_better')).toBeCloseTo(44.12, 1);
    expect(resolveAchievement(undefined, 0, 60, 'lower_better')).toBe(100);
    expect(resolveAchievement(undefined, 120, 100, 'higher_better')).toBeCloseTo(120);
    expect(resolveAchievement(undefined, null, 100, 'higher_better')).toBeNull();
    expect(resolveAchievement(undefined, 50, 0, 'higher_better')).toBeNull();
    expect(resolveAchievement(undefined, 50, 100, null)).toBeNull();
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
    // Absent fields: local direction-aware fallback. Lower-is-better: an increase is bad.
    expect(resolveMovementTone({ rawDelta: 0.03, direction: 'lower_better' })).toBe('bad');
    expect(resolveMovementTone({ rawDelta: -0.03, direction: 'lower_better' })).toBe('good');
    expect(resolveMovementTone({ rawDelta: 0, direction: 'lower_better' })).toBe('flat');
    expect(resolveMovementTone({ rawDelta: 0.03, direction: 'higher_better' })).toBe('good');
    expect(resolveMovementTone({ rawDelta: 0.03, direction: null })).toBe('unknown');
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

  it('uses the API achievement_percent for people to review when present', () => {
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
});
