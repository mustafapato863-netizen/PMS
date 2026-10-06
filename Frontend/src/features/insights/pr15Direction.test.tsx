import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import PeopleContributionAnalysis from '../../components/insights/PeopleContributionAnalysis';
import { kpiTrendRows } from '../../components/insights/kpiTrendRows';
import { buildPerformanceTrend, resolveAchievement, resolveMovementTone } from '../../components/insights/overview/insightsOverviewModel';
import { pr15Detail, pr15KpiTrend, pr15PeopleRows, pr15WatchItem } from './pr15Direction.fixture';
import { SEVERITY_LABELS, severityDisplay } from './severity';

// Real responses from the #13 + #14 + #15 merge: Initial Rejection Rate (lower-better) rose 4.5% → 5.5%.
describe('PR #15 response shape', () => {
  it('reads the rising lower-better detail as declining: red, with an UP arrow from raw_change', () => {
    expect(resolveMovementTone({
      trendStatus: pr15Detail.trend_status, changeValue: pr15Detail.change_value, rawDelta: pr15Detail.raw_change, direction: pr15Detail.direction,
    })).toBe('bad');
    expect(pr15Detail.raw_change).toBeGreaterThan(0);
    expect(resolveAchievement(pr15Detail.achievement_percent, pr15Detail.current_value, pr15Detail.target_value, pr15Detail.direction)).toBe(90.91);
  });

  it('plots the API achievement_percent and status on the KPI trends', () => {
    const measured = buildPerformanceTrend(pr15KpiTrend).filter((point) => point.actual !== null);
    expect(measured.map((point) => point.actual)).toEqual([100, 90.91]);
    expect(measured[1].raw).toMatchObject({ trendStatus: 'declining', status: 'at_risk' });
    const rows = kpiTrendRows(pr15KpiTrend).filter((row) => row.actual !== null);
    expect(rows.map((row) => row.status)).toEqual(['on_track', 'at_risk']);
  });

  it('colours the real people rows by trend_status: E1 rose (bad, ▲), E2 fell (good, ▼)', () => {
    render(
      <PeopleContributionAnalysis
        analysis={{
          kpi_key: pr15KpiTrend.kpi_key, kpi_label: pr15KpiTrend.kpi_label, unit: '%', direction: 'lower_better',
          total_employees: 2, negative_contributors: 2, positive_contributors: 0, data_issues: 0,
          rows: pr15PeopleRows.map((row) => ({ ...row, classification: 'negative' as const })),
        }}
        onOpenEmployee={() => undefined}
        renderEmployeeActions={() => null}
      />,
    );
    const cells = screen.getAllByTestId('contribution-trend');
    expect(cells.map((cell) => cell.getAttribute('data-tone'))).toEqual(['bad', 'good']);
    expect(cells[0].querySelector('svg')).toHaveClass('lucide-arrow-up');
    expect(cells[1].querySelector('svg')).toHaveClass('lucide-arrow-down');
  });

  it('labels the on-target-but-worsening information item as Watch', () => {
    expect(pr15WatchItem.severity).toBe('information');
    expect(SEVERITY_LABELS[severityDisplay(pr15WatchItem)]).toBe('Watch');
    expect(SEVERITY_LABELS[severityDisplay({ severity: 'information', insight_type: 'data_quality' })]).toBe('Data issue');
  });
});
