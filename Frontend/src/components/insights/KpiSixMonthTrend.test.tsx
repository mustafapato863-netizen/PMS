import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import type { InsightKpiTrend } from '../../features/insights/types';
import KpiSixMonthTrend from './KpiSixMonthTrend';
import { kpiTrendRows } from './kpiTrendRows';

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  LineChart: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  CartesianGrid: () => null,
  Legend: () => null,
  Line: () => null,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: ({ reversed }: { reversed?: boolean }) => (
    <div data-testid="trend-y-axis" data-reversed={String(Boolean(reversed))} />
  ),
}));

const baseTrend: InsightKpiTrend = {
  kpi_key: 'initial_error_rate',
  kpi_label: 'Initial Error Rate',
  unit: '%',
  direction: 'higher_better',
  points: [{
    period: { key: '2026-06', month: 'June', year: 2026 },
    actual_value: 0.017,
    target_value: 0.03,
    measured_records: 1,
  }],
};

describe('KpiSixMonthTrend axis direction', () => {
  it('reverses the Y axis when lower values are better', () => {
    render(<KpiSixMonthTrend trend={{ ...baseTrend, direction: 'lower_better' }} />);

    expect(screen.getByTestId('trend-y-axis')).toHaveAttribute('data-reversed', 'true');
    expect(screen.getByTestId('kpi-trend-direction')).toHaveTextContent('Lower is better (axis reversed)');
  });

  it('keeps the standard Y axis for higher-better KPIs', () => {
    render(<KpiSixMonthTrend trend={baseTrend} />);

    expect(screen.getByTestId('trend-y-axis')).toHaveAttribute('data-reversed', 'false');
    expect(screen.queryByTestId('kpi-trend-direction')).not.toBeInTheDocument();
  });
});

describe('kpiTrendRows per-point status', () => {
  const point = (key: string, actual: number | null, extra = {}) => ({
    period: { key, month: key.endsWith('05') ? 'May' : 'June', year: 2026 }, actual_value: actual, target_value: 0.05, measured_records: 1, ...extra,
  });

  it('derives lower-better status locally when the API has no status', () => {
    const rows = kpiTrendRows({ ...baseTrend, direction: 'lower_better', points: [point('2026-05', 0.04), point('2026-06', 0.1)] });
    // 0.05 / 0.04 = 125% (on track, below the line on a reversed axis = better); 0.05 / 0.1 = 50% (critical).
    expect(rows.map((row) => row.status)).toEqual(['on_track', 'critical']);
    expect(rows[0].achievement).toBeCloseTo(125);
  });

  it('derives higher-better status locally when the API has no status', () => {
    const rows = kpiTrendRows({ ...baseTrend, points: [point('2026-05', 0.04), point('2026-06', 0.03)] });
    expect(rows.map((row) => row.status)).toEqual(['at_risk', 'critical']);
  });

  it('prefers the API status and achievement_percent, and leaves unmeasured months without status', () => {
    const rows = kpiTrendRows({
      ...baseTrend,
      direction: 'lower_better',
      points: [point('2026-05', 0.04, { achievement_percent: 100, status: 'on_track' }), point('2026-06', null, { status: null })],
    });
    expect(rows[0]).toMatchObject({ achievement: 100, status: 'on_track' });
    expect(rows[1]).toMatchObject({ achievement: null, status: null });
  });

  it('does not guess a status for an unknown direction without API fields', () => {
    const rows = kpiTrendRows({ ...baseTrend, direction: null, points: [point('2026-06', 0.04)] });
    expect(rows[0].status).toBeNull();
    const withApi = kpiTrendRows({ ...baseTrend, direction: null, points: [point('2026-06', 0.04, { achievement_percent: 80, status: 'at_risk' })] });
    expect(withApi[0].status).toBe('at_risk');
  });
});
