import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { StoryBlockData, StoryReportBlock } from '../../../features/reports/types';
import BlockRenderer from './BlockRenderer';

const block = (type: string): StoryReportBlock => ({
  id: type, type, slot: 'full', config: {
    metrics: [], comparison: true, number_format: 'standard', row_limit: 10,
    sort_direction: 'desc', show_icons: true, show_subtitle: true,
    show_data_labels: true, show_target: true, narrative_mode: 'auto',
    include_evidence: true, include_recommendations: true, max_length: 700,
    scope_override: {},
  },
});

const data = (type: string, payload: Record<string, unknown>): StoryBlockData => ({
  block_id: type, block_type: type, state: 'ready', data: payload,
  warnings: [], source_periods: ['June 2026', 'May 2026'],
});

describe('management analysis block renderers', () => {
  it('renders the canonical movement bridge and reconciliation state', () => {
    const type = 'overall_score_movement_bridge';
    render(<BlockRenderer block={block(type)} blockData={data(type, {
      previous_overall_score: 86.1, current_overall_score: 85.4,
      total_score_point_change: -0.7, comparison_period: 'May 2026', current_period: 'June 2026',
      matched_employee_count: 12, joiner_count: 1, leaver_count: 0,
      kpi_contribution_movements: [{ label: 'Attendance', score_point_change: -0.6 }],
      team_contribution_movements: [], joiner_effect: -0.1, leaver_effect: 0,
      population_scope_mix_effect: 0, configuration_version_effect: 0,
      missing_incomparable_data_effect: 0, residual: 0,
      reconciliation_state: 'reconciled', narrative: 'Attendance contributed to the decline.', warnings: [],
    })} />);
    expect(screen.getByText('Attendance contributed to the decline.')).toBeInTheDocument();
    expect(screen.getByText(/reconciled/i)).toBeInTheDocument();
    expect(screen.getByText('12 matched · 1 joiners · 0 leavers')).toBeInTheDocument();
  });

  it('shows a scoring-basis change even when the configuration effect is zero', () => {
    const type = 'overall_score_movement_bridge';
    render(<BlockRenderer block={block(type)} blockData={data(type, {
      previous_overall_score: 80, current_overall_score: 80,
      total_score_point_change: 0, comparison_period: 'July 2026', current_period: 'August 2026',
      matched_employee_count: 2, joiner_count: 0, leaver_count: 0,
      kpi_contribution_movements: [], team_contribution_movements: [],
      joiner_effect: 0, leaver_effect: 0, population_scope_mix_effect: 0,
      configuration_version_effect: 0, scoring_basis_changed: true, raw_performance_changed: false,
      missing_incomparable_data_effect: 0, residual: 0, reconciliation_state: 'reconciled',
      narrative: 'Evaluation settings changed. Overall PMS Score was unchanged at 80.0% on each month\'s own applied basis.',
      warnings: [],
    })} />);
    expect(screen.getByText('Scoring basis changed')).toBeInTheDocument();
    expect(screen.getByText(/was unchanged at 80.0%/)).toBeInTheDocument();
  });

  it('lets a fresh source or formula context govern the raw movement label', () => {
    const type = 'overall_score_movement_bridge';
    render(<BlockRenderer block={block(type)} blockData={data(type, {
      previous_overall_score: 80, current_overall_score: 80,
      total_score_point_change: 0, comparison_period: 'July 2026', current_period: 'August 2026',
      matched_employee_count: 2, joiner_count: 0, leaver_count: 0,
      kpi_contribution_movements: [], team_contribution_movements: [],
      joiner_effect: 0, leaver_effect: 0, population_scope_mix_effect: 0,
      configuration_version_effect: 0, scoring_basis_changed: false, raw_performance_changed: true,
      missing_incomparable_data_effect: 0, residual: 0, reconciliation_state: 'reconciled',
      narrative: 'Overall PMS Score was unchanged at 80.0% on each month\'s own applied basis.',
      basis_context: {
        state: 'changed', raw_performance: 'not_comparable',
        message: 'Scores can be affected by evaluation settings. Comparable raw performance is not available.',
      },
      warnings: [],
    })} />);
    expect(screen.getByTestId('basis-comparison-note')).toHaveTextContent('Comparable raw performance is not available.');
    expect(screen.queryByText('Raw performance changed')).not.toBeInTheDocument();
    expect(screen.queryByText('Scoring basis changed')).not.toBeInTheDocument();
    expect(screen.getByText(/was unchanged at 80.0%/)).toBeInTheDocument();
    expect(screen.getAllByText('80%').length).toBeGreaterThan(0);
  });

  it('does not show an unqualified raw label when evidence is missing', () => {
    const type = 'overall_score_movement_bridge';
    render(<BlockRenderer block={block(type)} blockData={data(type, {
      previous_overall_score: 86.1, current_overall_score: 85.4,
      total_score_point_change: -0.7, comparison_period: 'May 2026', current_period: 'June 2026',
      matched_employee_count: 12, joiner_count: 1, leaver_count: 0,
      kpi_contribution_movements: [], team_contribution_movements: [],
      joiner_effect: -0.1, leaver_effect: 0, population_scope_mix_effect: 0,
      configuration_version_effect: 0, scoring_basis_changed: true, raw_performance_changed: true,
      missing_incomparable_data_effect: 0, residual: 0, reconciliation_state: 'partial',
      narrative: 'Attendance contributed to the decline.',
      basis_context: {
        state: 'unknown', raw_performance: 'unknown',
        message: 'Evaluation settings for this comparison are unavailable, so this score movement is not confirmed as like-for-like.',
      },
      warnings: [],
    })} />);
    expect(screen.getByTestId('basis-comparison-note')).toHaveTextContent('not confirmed as like-for-like');
    expect(screen.queryByText('Raw performance changed')).not.toBeInTheDocument();
    expect(screen.queryByText('Scoring basis changed')).not.toBeInTheDocument();
    expect(screen.getByText('Attendance contributed to the decline.')).toBeInTheDocument();
    expect(screen.getByText(/partial/i)).toBeInTheDocument();
  });

  it('period-labels a fresh trend context instead of an unqualified basis badge', () => {
    const type = 'score_trend';
    render(<BlockRenderer block={block(type)} blockData={data(type, {
      series: [
        { label: 'July 2026', value: 82.85, basis_changed: true, basis_state: 'uniform', basis_context: { message: 'Evaluation settings comparison is unavailable for the exact previous month.' } },
        { label: 'August 2026', value: 80, basis_changed: true, basis_state: 'mixed', basis_context: { message: 'Scores can be affected by evaluation settings. Comparable raw performance is not available.' } },
      ],
    })} />);
    const note = screen.getByTestId('basis-comparison-note');
    expect(note).toHaveTextContent('July 2026: Evaluation settings comparison is unavailable for the exact previous month.');
    expect(note).toHaveTextContent('August 2026: Scores can be affected by evaluation settings.');
    expect(screen.queryByText('Mixed basis')).not.toBeInTheDocument();
    expect(screen.queryByText('Basis changed')).not.toBeInTheDocument();
  });

  it('labels a trend point whose month uses a different applied basis', () => {
    const type = 'score_trend';
    render(<BlockRenderer block={block(type)} blockData={data(type, {
      series: [
        { label: 'July 2026', value: 82.85, basis_changed: false, basis_state: 'uniform' },
        { label: 'August 2026', value: 80, basis_changed: true, basis_state: 'mixed' },
      ],
    })} />);
    expect(screen.getByText('Mixed basis')).toBeInTheDocument();
    expect(screen.queryByText('Basis changed')).not.toBeInTheDocument();
  });

  it('separates zero-target configuration exclusions from ranked KPIs', () => {
    const type = 'lowest_kpis_weighted_impact';
    render(<BlockRenderer block={block(type)} blockData={data(type, {
      rows: [{ rank: 1, name: 'Attendance', team: 'Inbound', actual: 60, target: 75, lost_points: 8.5 }],
      configuration_issues_excluded: [{ name: 'Zero Target KPI' }],
    })} />);
    expect(screen.getByText('Attendance')).toBeInTheDocument();
    expect(screen.getByText('1 configuration issue(s) excluded from ranking.')).toBeInTheDocument();
  });

  it('discloses employees excluded for insufficient consecutive history', () => {
    const type = 'three_month_consecutive_low_performers';
    render(<BlockRenderer block={block(type)} blockData={data(type, {
      rows: [], insufficient_history: [{ employee: 'Employee A' }],
    })} />);
    expect(screen.getByText('1 employee(s) have insufficient consecutive history and were not classified.')).toBeInTheDocument();
  });
});
