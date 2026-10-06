import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { ExecutiveTrendPoint } from '../../../features/executive/types';
import ScoreTrendChart from './ScoreTrendChart';

function point(month: string, key: string, score: number | null): ExecutiveTrendPoint {
  return {
    period: { year: 2026, month, key },
    score,
    comparison_score: null,
    target: 100,
    measured_records: 14,
  };
}

const points = [
  point('January', '2026-01', 80),
  point('February', '2026-02', 82),
  point('March', '2026-03', 83),
  point('April', '2026-04', 81),
  point('May', '2026-05', 85),
  point('June', '2026-06', 87),
];

describe('ScoreTrendChart', () => {
  it('shows a point tooltip and moves between measured months with the keyboard', () => {
    render(<ScoreTrendChart points={points} title="Performance" comparisonLabel="Company average" />);

    const june = screen.getByTestId('executive-trend-point-2026-06');
    june.focus();
    expect(screen.getByTestId('executive-trend-tooltip')).toHaveTextContent('Jun 2026');
    expect(screen.getByTestId('executive-trend-tooltip')).toHaveTextContent('87.0%');

    fireEvent.keyDown(june, { key: 'ArrowLeft' });
    expect(screen.getByTestId('executive-trend-tooltip')).toHaveTextContent('May 2026');
  });

  it('keeps gaps in score history visible instead of connecting across missing months', () => {
    const withGap = [
      point('January', '2026-01', 80),
      point('February', '2026-02', 82),
      point('March', '2026-03', null),
      point('April', '2026-04', 81),
      point('May', '2026-05', 85),
      point('June', '2026-06', 87),
    ];

    render(<ScoreTrendChart points={withGap} title="Performance" />);
    expect(screen.getAllByTestId('executive-trend-series')).toHaveLength(2);
  });

  it('shows an explicit empty state when the selected scope has no measured scores', () => {
    const noData = points.map((entry) => ({ ...entry, score: null }));
    render(<ScoreTrendChart points={noData} title="Performance" />);
    expect(screen.getByTestId('executive-trend-empty')).toHaveTextContent('No measured score');
  });
});
