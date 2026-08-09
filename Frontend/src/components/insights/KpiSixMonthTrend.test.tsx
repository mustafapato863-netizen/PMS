import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import type { InsightKpiTrend } from '../../features/insights/types';
import KpiSixMonthTrend from './KpiSixMonthTrend';

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
  });

  it('keeps the standard Y axis for higher-better KPIs', () => {
    render(<KpiSixMonthTrend trend={baseTrend} />);

    expect(screen.getByTestId('trend-y-axis')).toHaveAttribute('data-reversed', 'false');
  });
});
