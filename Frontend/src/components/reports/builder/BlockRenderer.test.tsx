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
