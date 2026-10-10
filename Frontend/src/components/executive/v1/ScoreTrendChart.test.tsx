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

  it('shows one settings note and repeats it on the active month tooltip', () => {
    const noted = points.map((item, index) => index === points.length - 1 ? {
      ...item,
      basis_context: {
        state: 'changed' as const,
        like_for_like: false,
        raw_performance: 'unchanged' as const,
        membership: 'stable' as const,
        reasons: ['target'],
        message: 'Scores can be affected by evaluation settings. Comparable raw performance is unchanged.',
      },
    } : item);
    render(<ScoreTrendChart points={noted} title="Performance" />);

    expect(screen.getAllByTestId('basis-comparison-note')).toHaveLength(1);
    fireEvent.focus(screen.getByTestId('executive-trend-point-2026-06'));
    expect(screen.getByTestId('executive-trend-tooltip')).toHaveTextContent('Scores can be affected by evaluation settings.');
    expect(screen.getByTestId('executive-trend-tooltip')).toHaveTextContent('Comparable raw performance is unchanged.');
  });

  it('keeps the current comparison note and leaves older notes on the focused month', () => {
    const unavailable = 'Evaluation settings comparison is unavailable for the exact previous month.';
    const changed = 'Scores can be affected by evaluation settings. Comparable raw performance changed.';
    const withHistory = points.map((item) => {
      if (item.period.key === '2026-05') return { ...item, basis_context: { state: 'unknown' as const, like_for_like: false, raw_performance: 'unknown' as const, membership: 'none' as const, reasons: [], message: unavailable } };
      if (item.period.key === '2026-04') return { ...item, basis_context: { state: 'changed' as const, like_for_like: false, raw_performance: 'changed' as const, membership: 'stable' as const, reasons: ['target'], message: changed } };
      return item;
    });
    render(<ScoreTrendChart points={withHistory} title="Performance" />);

    expect(screen.queryByTestId('basis-comparison-note')).not.toBeInTheDocument();
    fireEvent.focus(screen.getByTestId('executive-trend-point-2026-04'));
    const older = screen.getByTestId('executive-trend-tooltip');
    expect(older).toHaveTextContent(changed);
    expect(older).not.toHaveTextContent(unavailable);
    expect(older.querySelector('[data-testid="basis-comparison-note"]')).toBeNull();

    fireEvent.focus(screen.getByTestId('executive-trend-point-2026-05'));
    expect(screen.getByTestId('executive-trend-tooltip')).toHaveTextContent(unavailable);
    expect(screen.queryByTestId('basis-comparison-note')).not.toBeInTheDocument();
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
