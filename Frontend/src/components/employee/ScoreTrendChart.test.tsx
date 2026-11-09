import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import {
  ProfileKpiSixMonthTrend,
  type SixMonthKpiPoint,
  type SixMonthKpiSeriesItem,
} from './ScoreTrendChart';
import ScoreTrendChart from './ScoreTrendChart';
import { CustomTooltip } from './ScoreTrendChart';

it('shows no data in the tooltip for a missing score', () => {
  render(<CustomTooltip active label="Aug" payload={[{ value: null, color: 'blue', dataKey: 'score', name: 'Actual Score' }]} />);
  expect(screen.getByText('Aug')).toBeInTheDocument();
  expect(screen.getByText('No data')).toBeInTheDocument();
});

it('distinguishes unavailable scoring evidence from a missing month', () => {
  render(<CustomTooltip active label="Aug" payload={[{ value: null, color: 'blue', dataKey: 'score', name: 'Actual Score', payload: { month: 'Aug', score: null, basisDetail: 'Scoring basis unavailable' } }]} />);
  expect(screen.getByText('Scoring basis unavailable')).toBeInTheDocument();
  expect(screen.queryByText('No data')).not.toBeInTheDocument();
});

function point(
  month: string,
  periodKey: string,
  actual: number | null,
  target: number | null,
): SixMonthKpiPoint {
  const format = (value: number | null) =>
    value === null ? '—' : `${value.toFixed(1)}%`;
  return {
    month,
    periodKey,
    actual,
    target,
    actualFormatted: format(actual),
    targetFormatted: format(target),
    metTarget:
      actual === null || target === null
        ? null
        : actual <= target + 1e-9
        ? true
        : false,
  };
}

function series(
  id: string,
  kpiKey: string,
  betterDirection: 'higher' | 'lower',
  trend6Mo: SixMonthKpiPoint[],
): SixMonthKpiSeriesItem {
  const last = trend6Mo[trend6Mo.length - 1];
  return {
    id,
    kpiKey,
    name: id,
    shortName: id,
    unit: '%',
    betterDirection,
    actualDisplay: last?.actualFormatted ?? '—',
    targetDisplay: last?.targetFormatted ?? '—',
    achievementPct: 0,
    gapLabel: 'Below target',
    diagnosis: '',
    trend6Mo,
  };
}

const lowerSeries = series('rejection', 'rejection', 'lower', [
  point('Apr', '2026-04', 0.0, 1.0),
  point('May', '2026-05', 0.6, 1.0),
  point('Jun', '2026-06', 1.0, 1.0),
  point('Jul', '2026-07', 1.6, 1.0),
  point('Aug', '2026-08', 2.3, 1.0),
  point('Sep', '2026-09', 3.0, 1.0),
]);

const higherSeries = series('quality', 'quality', 'higher', [
  point('Apr', '2026-04', 80, 90),
  point('May', '2026-05', 85, 90),
  point('Jun', '2026-06', 90, 90),
  point('Jul', '2026-07', 95, 90),
  point('Aug', '2026-08', 88, 90),
  point('Sep', '2026-09', 92, 90),
]);

function Harness({ kpis }: { kpis: SixMonthKpiSeriesItem[] }) {
  const [selectedId, setSelectedId] = useState(kpis[0].id);
  return (
    <ProfileKpiSixMonthTrend
      kpis={kpis}
      selectedId={selectedId}
      onSelectKpi={setSelectedId}
    />
  );
}

function targetYs() {
  const target = screen.getByTestId('role-kpi-chart').querySelector('[data-series="target"]');
  expect(target).toBeTruthy();
  if (target?.tagName.toLowerCase() === 'polyline') {
    return (target.getAttribute('points') ?? '')
      .trim()
      .split(/\s+/)
      .map((pair) => Number(pair.split(',')[1]));
  }
  return [Number(target?.getAttribute('y1'))];
}

function cy(testId: string): number {
  const node = screen.getByTestId(testId);
  return Number(node.getAttribute('cy'));
}

function cx(testId: string): number {
  const node = screen.getByTestId(testId);
  return Number(node.getAttribute('cx'));
}

describe('ProfileKpiSixMonthTrend direction handling', () => {
  it('reverses a lower-is-better KPI around the maximum acceptable target', () => {
    render(<Harness kpis={[lowerSeries]} />);

    const targetY = targetYs()[0];
    expect(targetY).toBeGreaterThan(0);

    // 0.0 and 0.6 are above the dashed maximum-acceptable line; 1.0 sits on it.
    expect(cy('trend-peak-2026-04')).toBeLessThan(cy('trend-dot-2026-05'));
    expect(cy('trend-dot-2026-05')).toBeLessThan(targetY);
    expect(cy('trend-dot-2026-06')).toBeCloseTo(targetY, 0);

    // 1.6, 2.3, and 3.0 stay visible below the line, in descending value order.
    expect(cy('trend-dot-2026-07')).toBeGreaterThan(targetY);
    expect(cy('trend-dot-2026-08')).toBeGreaterThan(cy('trend-dot-2026-07'));
    expect(cy('trend-dot-2026-09')).toBeGreaterThan(cy('trend-dot-2026-08'));

    // Months remain chronological left-to-right.
    const cxs = [
      cx('trend-peak-2026-04'),
      cx('trend-dot-2026-05'),
      cx('trend-dot-2026-06'),
      cx('trend-dot-2026-07'),
      cx('trend-dot-2026-08'),
      cx('trend-dot-2026-09'),
    ];
    expect(cxs).toEqual([...cxs].sort((a, b) => a - b));

    // 0.0 is the best month and keeps the trophy.
    expect(screen.getByTestId('trend-peak-2026-04')).toBeInTheDocument();
    expect(screen.queryByTestId('trend-dot-2026-04')).not.toBeInTheDocument();

    // Met/missed colouring follows actual <= each month's target.
    expect(screen.getByTestId('trend-dot-2026-05')).toHaveAttribute('data-missed', 'false');
    expect(screen.getByTestId('trend-dot-2026-06')).toHaveAttribute('data-missed', 'false');
    expect(screen.getByTestId('trend-dot-2026-07')).toHaveAttribute('data-missed', 'true');
    expect(screen.getByTestId('trend-dot-2026-08')).toHaveAttribute('data-missed', 'true');
    expect(screen.getByTestId('trend-dot-2026-09')).toHaveAttribute('data-missed', 'true');

    expect(screen.getByTestId('target-direction-label')).toHaveTextContent(
      'Maximum acceptable ≤ 1.0%',
    );
    expect(screen.getByText('3 / 6')).toBeInTheDocument();
  });

  it('keeps each month’s own target and shows unavailable months', () => {
    const changingTarget = series('rejection', 'rejection', 'lower', [
      point('Apr', '2026-04', 0.0, 0.5),
      point('May', '2026-05', 0.8, 1.0),
      point('Jun', '2026-06', null, 1.0),
      point('Jul', '2026-07', 2.0, 1.5),
    ]);

    render(<ProfileKpiSixMonthTrend kpis={[changingTarget]} selectedId="rejection" onSelectKpi={() => {}} />);

    const ys = targetYs();
    expect(ys).toHaveLength(4);
    expect(new Set(ys.map((y) => y.toFixed(1))).size).toBeGreaterThan(1);
    expect(screen.getByTestId('no-data-marker-2026-06')).toHaveTextContent('Unavailable');
    expect(screen.queryByTestId('trend-point-2026-06')).not.toBeInTheDocument();
    expect(screen.getByTestId('trend-peak-2026-04')).toBeInTheDocument();
  });

  it('restores the standard direction when switching to a higher-is-better KPI', () => {
    render(<Harness kpis={[lowerSeries, higherSeries]} />);

    expect(screen.getByTestId('target-direction-label')).toHaveTextContent(
      'Maximum acceptable ≤ 1.0%',
    );
    expect(cy('trend-peak-2026-04')).toBeLessThan(cy('trend-dot-2026-09'));

    fireEvent.click(screen.getByTestId('trend-kpi-switcher-quality'));

    expect(screen.getByTestId('target-direction-label')).toHaveTextContent(
      'Minimum acceptable ≥ 90.0%',
    );

    // Higher values now render higher (smaller SVG y).
    expect(cy('trend-dot-2026-05')).toBeGreaterThan(cy('trend-dot-2026-06'));
    expect(cy('trend-dot-2026-06')).toBeGreaterThan(cy('trend-peak-2026-07'));
    expect(cy('trend-dot-2026-09')).toBeLessThan(cy('trend-dot-2026-05'));

    expect(screen.getByTestId('trend-peak-2026-07')).toBeInTheDocument();
    expect(screen.getByTestId('trend-dot-2026-09')).toHaveAttribute('data-missed', 'false');
    expect(screen.getByTestId('trend-dot-2026-05')).toHaveAttribute('data-missed', 'true');
  });
});

describe('employee score trend', () => {
  it('reads numeric scores and leaves a missing month as no data', () => {
    render(
      <ScoreTrendChart
        data={[
          { month: 'Aug', score: 80, isPeak: true },
          { month: 'Sep', score: null, selected: true },
        ]}
        targetScore={100}
        targetLabel="100% target"
        animate={false}
      />,
    );

    expect(screen.getByText(/Aug: 80\.0%/)).toBeInTheDocument();
    expect(screen.getByText(/Sep: No data \(selected\)/)).toBeInTheDocument();
    expect(screen.getByText(/100% target/)).toBeInTheDocument();
  });
});
