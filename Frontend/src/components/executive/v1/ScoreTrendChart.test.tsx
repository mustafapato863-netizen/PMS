import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
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
  afterEach(() => vi.unstubAllGlobals());

  it('keeps observing the chart container when an empty filter gains data', () => {
    const observed: Element[] = [];
    let resize: ResizeObserverCallback | undefined;
    vi.stubGlobal('ResizeObserver', class {
      constructor(callback: ResizeObserverCallback) { resize = callback; }
      observe(element: Element) { observed.push(element); }
      disconnect() {}
    });
    const { rerender } = render(<ScoreTrendChart points={[]} title="Performance" />);
    expect(observed).toHaveLength(1);
    rerender(<ScoreTrendChart points={points} title="Performance" />);
    const chart = screen.getByTestId('executive-trend-chart');
    expect(observed[0]).toContainElement(chart);
    act(() => resize?.([{ contentRect: { width: 320 } } as ResizeObserverEntry], {} as ResizeObserver));
    expect(chart).toHaveAttribute('width', '320');
  });

  it('shows a point tooltip and moves between measured months with the keyboard', () => {
    render(<ScoreTrendChart points={points} title="Performance" comparisonLabel="Company average" />);

    const june = screen.getByTestId('executive-trend-point-2026-06');
    fireEvent.focus(june);
    expect(screen.getByTestId('executive-trend-tooltip')).toHaveTextContent('Jun 2026');
    expect(screen.getByTestId('executive-trend-tooltip')).toHaveTextContent('87.0%');
    expect(screen.getByTestId('executive-trend-tooltip')).toHaveTextContent('+2.0%');
    expect(screen.getByTestId('executive-trend-tooltip')).not.toHaveTextContent(/\b(?:pp|pts)\b/);

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

  it('treats non-finite scores as missing instead of drawing invalid points or score labels', () => {
    render(<ScoreTrendChart points={[point('January', '2026-01', NaN), point('February', '2026-02', Infinity)]} title="Function" />);
    expect(screen.getByTestId('executive-trend-empty')).toBeVisible();
    expect(screen.queryByTestId('function-trend-value')).not.toBeInTheDocument();
  });
});
