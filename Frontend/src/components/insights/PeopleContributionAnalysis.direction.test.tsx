import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import PeopleContributionAnalysis from './PeopleContributionAnalysis';
import type { InsightPeopleContributionAnalysis, InsightPersonContribution } from '../../features/insights/types';

const row = (id: string, trend: number | null, direction: InsightPersonContribution['direction']): InsightPersonContribution => ({
  employee_id: id, employee_name: `Person ${id}`, team: 'RCM', performance_level: 'Employee', position: 'Agent',
  kpi_key: 'rejection_rate', kpi_label: 'Rejection Rate', unit: '%', direction,
  current_value: 0.12, target_value: 0.05, gap: -0.07, weighted_impact: -1, trend, severity: 'High', classification: 'negative',
});

const analysis = (rows: InsightPersonContribution[], direction: InsightPeopleContributionAnalysis['direction'] = 'lower_better'): InsightPeopleContributionAnalysis => ({
  kpi_key: 'rejection_rate', kpi_label: 'Rejection Rate', unit: '%', direction,
  total_employees: rows.length, negative_contributors: rows.length, positive_contributors: 0, data_issues: 0, rows,
});

function tones() {
  return screen.getAllByTestId('contribution-trend').map((cell) => cell.getAttribute('data-tone'));
}

describe('PeopleContributionAnalysis trend direction', () => {
  it('shows a rising lower-is-better KPI as worsening and a falling one as improving', () => {
    render(
      <PeopleContributionAnalysis
        analysis={analysis([row('1', 0.03, 'lower_better'), row('2', -0.02, 'lower_better'), row('3', 0.03, 'higher_better')])}
        onOpenEmployee={() => undefined}
        renderEmployeeActions={() => null}
      />,
    );
    expect(tones()).toEqual(['bad', 'good', 'good']);
    const [rising, falling] = screen.getAllByTestId('contribution-trend');
    expect(rising).toHaveClass('text-rose-600');
    expect(falling).toHaveClass('text-emerald-600');
  });

  it('keeps flat and unknown-direction trends neutral instead of red', () => {
    render(
      <PeopleContributionAnalysis
        analysis={analysis([row('1', 0, 'lower_better'), row('2', 0.04, null), row('3', null, 'lower_better')], null)}
        onOpenEmployee={() => undefined}
        renderEmployeeActions={() => null}
      />,
    );
    expect(tones()).toEqual(['flat', 'unknown', 'unknown']);
    screen.getAllByTestId('contribution-trend').forEach((cell) => expect(cell).toHaveClass('text-[var(--text-muted)]'));
  });

  it('falls back to the analysis direction when a row has none', () => {
    render(
      <PeopleContributionAnalysis
        analysis={analysis([row('1', 0.03, null)], 'lower_better')}
        onOpenEmployee={() => undefined}
        renderEmployeeActions={() => null}
      />,
    );
    expect(tones()).toEqual(['bad']);
  });

  it('uses the API trend_status for colour while the arrow follows the raw trend', () => {
    render(
      <PeopleContributionAnalysis
        analysis={analysis([
          { ...row('1', 0.03, null), trend_status: 'declining', change_value: -0.03 },
          { ...row('2', -0.02, null), trend_status: 'improving', change_value: 0.02 },
          { ...row('3', 0.03, 'higher_better'), trend_status: 'improving', change_value: 0.03 },
          { ...row('4', 0, 'lower_better'), trend_status: 'stable', change_value: 0 },
        ], null)}
        onOpenEmployee={() => undefined}
        renderEmployeeActions={() => null}
      />,
    );
    expect(tones()).toEqual(['bad', 'good', 'good', 'flat']);
    const cells = screen.getAllByTestId('contribution-trend');
    expect(cells[0].querySelector('svg')).toHaveClass('lucide-arrow-up');
    expect(cells[1].querySelector('svg')).toHaveClass('lucide-arrow-down');
    expect(cells[3].querySelector('svg')).toBeNull();
  });
});
