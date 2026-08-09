import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import type { InsightItem } from '../../features/insights/types';
import TeamPerformanceAnalysis from './TeamPerformanceAnalysis';

const insight = (overrides: Partial<InsightItem> = {}): InsightItem => ({
  id: 'booking-gap',
  severity: 'critical',
  insight_type: 'kpi_driver',
  title: 'Booking Conversion contributed to the performance gap',
  explanation: 'Booking Conversion decreased from 31.0% to 19.2% and missed the target of 46.0%.',
  scope: 'Outbound · Agent',
  impact_points: -6.4,
  trend_label: 'Compared with previous available period',
  priority_reason: 'Weighted contribution changed the overall score by 6.4%.',
  status: 'open',
  team: 'Outbound',
  performance_level: 'Employee',
  position: 'Agent',
  employee_id: null,
  kpi_key: 'booking_conversion',
  detail: {
    current_value: 19.2,
    previous_value: 31,
    target_value: 46,
    unit: '%',
    direction: 'higher_better',
    impact_points: -6.4,
    affected_teams: ['Outbound'],
    affected_positions: ['Agent'],
    affected_employees: [],
    evidence: [],
    warnings: [],
    recommended_focus: 'Increase Booking Conversion and review the affected employees with the largest gap.',
  },
  planning_context: {},
  ...overrides,
});

describe('TeamPerformanceAnalysis', () => {
  it('keeps the summary compact and reveals the canonical narrative on demand', async () => {
    const user = userEvent.setup();
    render(<TeamPerformanceAnalysis insights={[insight()]} />);

    expect(screen.getByRole('heading', { name: 'Performance Analysis' })).toBeInTheDocument();
    expect(screen.getByText('-6.4%')).toBeInTheDocument();
    expect(screen.queryByText(/decreased from 31.0%/)).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Booking Conversion contributed/ }));

    expect(screen.getByText(/decreased from 31.0%/)).toBeInTheDocument();
    expect(screen.getAllByText(/Increase Booking Conversion/).length).toBeGreaterThan(0);
  });

  it('omits employee-risk and data-quality items from the team KPI narrative', () => {
    render(<TeamPerformanceAnalysis insights={[insight({ insight_type: 'employee_risk' })]} />);
    expect(screen.queryByRole('heading', { name: 'Performance Analysis' })).not.toBeInTheDocument();
  });
});
