import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { InsightExecutiveStory, InsightOverallTrendPoint, InsightsWorkspace } from '../../../features/insights/types';
import ExecutiveSummary from './ExecutiveSummary';

const unavailable = 'Evaluation settings comparison is unavailable for the exact previous month.';
const changed = 'Scores can be affected by evaluation settings. Comparable raw performance changed.';

const story: InsightExecutiveStory = {
  headline: 'August performance',
  scope_label: 'Company',
  current_score: 80,
  target_score: 100,
  gap_points: -20,
  score_change: 0,
  primary_scope: null,
  primary_scope_contribution_percent: null,
  primary_driver: null,
  primary_driver_impact: null,
  recommended_focus: 'Keep the current comparison.',
  confidence: 'high',
  evidence: [],
};

const comparison: InsightsWorkspace['comparison'] = {
  current: { year: 2026, month: 'August', key: '2026-08' },
  previous: { year: 2026, month: 'July', key: '2026-07' },
  is_adjacent: true,
  note: null,
};

function point(month: string, key: string, score: number, message: string | null): InsightOverallTrendPoint {
  return {
    period: { year: 2026, month, key },
    score,
    target: 100,
    measured_records: 2,
    basis_context: message === null ? { state: 'unchanged', like_for_like: true, raw_performance: 'unchanged', reasons: [], message: null } : {
      state: message === changed ? 'changed' : 'unavailable',
      like_for_like: false,
      raw_performance: message === changed ? 'changed' : 'unknown',
      reasons: message === changed ? ['target'] : [],
      message,
    },
  };
}

describe('insights performance trend basis note', () => {
  it('keeps the current comparison and shows older notes only on the focused month', () => {
    render(<ExecutiveSummary story={story} comparison={comparison} trend={null} overallTrend={[
      point('June', '2026-06', 78, unavailable),
      point('July', '2026-07', 76, changed),
      point('August', '2026-08', 80, null),
    ]} />);

    expect(screen.queryByTestId('basis-comparison-note')).not.toBeInTheDocument();
    fireEvent.focus(screen.getByTestId('performance-trend-point-2026-07'));
    const older = screen.getByTestId('performance-trend-tooltip');
    expect(older).toHaveTextContent(changed);
    expect(older).not.toHaveTextContent(unavailable);
    expect(older.querySelector('[data-testid="basis-comparison-note"]')).toBeNull();

    fireEvent.focus(screen.getByTestId('performance-trend-point-2026-06'));
    expect(screen.getByTestId('performance-trend-tooltip')).toHaveTextContent(unavailable);
    expect(screen.queryByTestId('basis-comparison-note')).not.toBeInTheDocument();
    expect(screen.getByTestId('performance-trend-chart')).toBeInTheDocument();
  });
});
