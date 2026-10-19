import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import InsightsSummaryStrip from './InsightsSummaryStrip';
import type {
  InsightExecutiveStory,
  InsightItem,
  InsightKpiDiagnosisRow,
} from '../../../features/insights/types';

const mockStory: InsightExecutiveStory = {
  headline: 'Call Center performance improved',
  scope_label: 'Call Center',
  current_score: 88.5,
  target_score: 100,
  gap_points: -11.5,
  score_change: 2.3,
  primary_scope: 'Inbound',
  primary_scope_contribution_percent: 60,
  primary_driver: 'Booking Rate',
  primary_driver_impact: 1.5,
  recommended_focus: 'Focus on Outbound reachability',
  confidence: 'high',
  evidence: [],
  basis_context: {
    state: 'unchanged',
    like_for_like: true,
    raw_performance: 'unchanged',
    reasons: [],
    message: 'Evaluated on standard 2026 scorecard basis.',
  },
};

const mockRows: InsightKpiDiagnosisRow[] = [
  {
    key: 'booking',
    label: 'Booking Rate',
    unit: '%',
    direction: 'higher_better',
    weight: 0.35,
    actual: 85,
    target: 80,
    achievement_percent: 106.2,
    status: 'on_track',
    effect_points: 0.8,
    people_below_target: 2,
    six_months: [],
    most_below_team: null,
    other_cohorts: [],
    teams: ['Inbound'],
  },
  {
    key: 'attendance',
    label: 'Attendance Rate',
    unit: '%',
    direction: 'higher_better',
    weight: 0.25,
    actual: 91,
    target: 95,
    achievement_percent: 95.8,
    status: 'at_risk',
    effect_points: -0.4,
    people_below_target: 5,
    six_months: [],
    most_below_team: null,
    other_cohorts: [],
    teams: ['Inbound'],
  },
  {
    key: 'aht',
    label: 'AHT',
    unit: 'min',
    direction: 'lower_better',
    weight: 0.40,
    actual: 4.5,
    target: 3.0,
    achievement_percent: 66.7,
    status: 'critical',
    effect_points: -1.8,
    people_below_target: 12,
    six_months: [],
    most_below_team: null,
    other_cohorts: [],
    teams: ['Inbound'],
  },
];

const mockCriticalInsight: InsightItem = {
  id: 'crit-1',
  severity: 'critical',
  insight_type: 'kpi_driver',
  title: 'AHT exceeded upper limit',
  explanation: 'Average handle time is critically high',
  scope: 'Inbound',
  impact_points: -1.8,
  trend_label: 'Decline vs last month',
  priority_reason: 'High weighted drag',
  status: 'Open',
  team: 'Inbound',
  performance_level: 'Employee',
  position: null,
  employee_id: null,
  kpi_key: 'aht',
  detail: {
    current_value: 4.5,
    previous_value: 3.8,
    target_value: 3.0,
    unit: 'min',
    direction: 'lower_better',
    impact_points: -1.8,
    affected_teams: ['Inbound'],
    affected_positions: [],
    affected_employees: [],
    evidence: [],
    warnings: [],
    recommended_focus: 'Review call wrap-up times',
  },
  planning_context: {},
};

describe('InsightsSummaryStrip (High-Level Performance & Breakdown Summary)', () => {
  it('renders high-level performance cards (score, change, target benchmark, gap, grade)', () => {
    const onOpen = vi.fn();
    render(
      <InsightsSummaryStrip
        story={mockStory}
        rows={mockRows}
        criticalInsights={[]}
        onOpenInsight={onOpen}
      />
    );

    const section = screen.getByRole('region', { name: 'Summary' });
    expect(section).toBeInTheDocument();

    // Team score card
    expect(section).toHaveTextContent('Team score');
    expect(section).toHaveTextContent('88.5%');
    expect(section).toHaveTextContent('Grade C');
    expect(section).toHaveTextContent('+2.3 pts vs previous month');

    // Target benchmark & gap
    expect(section).toHaveTextContent('Target Benchmark');
    expect(section).toHaveTextContent('100.0%');
    expect(section).toHaveTextContent('−11.5 pts to target');

    // Analyzed KPIs card
    expect(section).toHaveTextContent('3 KPIs');
    expect(section).toHaveTextContent('2 of 3 KPIs below target');

    // Basis message
    expect(section).toHaveTextContent('Evaluated on standard 2026 scorecard basis.');
  });

  it('renders KPI health distribution breakdown bar with On Track, At Risk, and Critical counts', () => {
    const onOpen = vi.fn();
    render(
      <InsightsSummaryStrip
        story={mockStory}
        rows={mockRows}
        criticalInsights={[]}
        onOpenInsight={onOpen}
      />
    );

    expect(screen.getByText('KPI Health Distribution')).toBeInTheDocument();
    expect(screen.getByText(/1 on track/i)).toBeInTheDocument();
    expect(screen.getByText(/1 at risk/i)).toBeInTheDocument();
    expect(screen.getByText(/1 critical/i)).toBeInTheDocument();

    const progressBar = screen.getByRole('progressbar', { name: 'KPI health breakdown' });
    expect(progressBar).toBeInTheDocument();
    expect(progressBar).toHaveAttribute('aria-valuenow', '33');
  });

  it('opens and closes the Quick Help popover with metric guide', async () => {
    const user = userEvent.setup();
    render(
      <InsightsSummaryStrip
        story={mockStory}
        rows={mockRows}
        criticalInsights={[]}
        onOpenInsight={vi.fn()}
      />
    );

    const helpButton = screen.getByRole('button', { name: 'Quick help and metric guide' });
    expect(helpButton).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: 'Quick help and metric guide' })).not.toBeInTheDocument();

    // Click to open
    await user.click(helpButton);
    const dialog = screen.getByRole('dialog', { name: 'Quick help and metric guide' });
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveTextContent('Metric Guide & Quick Help');
    expect(dialog).toHaveTextContent('1. What is happening?');
    expect(dialog).toHaveTextContent('2. Why does it matter?');
    expect(dialog).toHaveTextContent('3. What action should you take?');

    // Click "Got it" to close
    const gotItBtn = screen.getByRole('button', { name: 'Got it' });
    await user.click(gotItBtn);
    expect(screen.queryByRole('dialog', { name: 'Quick help and metric guide' })).not.toBeInTheDocument();

    // Open again and close with Escape key
    await user.click(helpButton);
    expect(screen.getByRole('dialog', { name: 'Quick help and metric guide' })).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: 'Quick help and metric guide' })).not.toBeInTheDocument();
  });

  it('renders critical alert button when critical insights exist and triggers onOpenInsight', async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    render(
      <InsightsSummaryStrip
        story={mockStory}
        rows={mockRows}
        criticalInsights={[mockCriticalInsight]}
        onOpenInsight={onOpen}
      />
    );

    const alertBtn = screen.getByRole('button', {
      name: /1 critical alert: AHT exceeded upper limit/i,
    });
    expect(alertBtn).toBeInTheDocument();

    await user.click(alertBtn);
    expect(onOpen).toHaveBeenCalledWith(mockCriticalInsight);
  });

  it('cycles through multiple critical alerts using next and previous buttons', async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    const secondCritical: InsightItem = {
      ...mockCriticalInsight,
      id: 'crit-2',
      title: 'Inbound Rejection Rate spiked',
    };

    render(
      <InsightsSummaryStrip
        story={mockStory}
        rows={mockRows}
        criticalInsights={[mockCriticalInsight, secondCritical]}
        onOpenInsight={onOpen}
      />
    );

    // Initial alert (1 of 2)
    expect(screen.getByText(/2 critical alerts: AHT exceeded upper limit/i)).toBeInTheDocument();
    expect(screen.getByText('1 of 2')).toBeInTheDocument();

    // Click Next
    const nextBtn = screen.getByRole('button', { name: 'Next alert' });
    await user.click(nextBtn);
    expect(screen.getByText(/2 critical alerts: Inbound Rejection Rate spiked/i)).toBeInTheDocument();
    expect(screen.getByText('2 of 2')).toBeInTheDocument();

    // Click View Details on second alert
    const viewDetailsBtn = screen.getByRole('button', { name: 'View Details' });
    await user.click(viewDetailsBtn);
    expect(onOpen).toHaveBeenCalledWith(secondCritical);

    // Click Prev
    const prevBtn = screen.getByRole('button', { name: 'Previous alert' });
    await user.click(prevBtn);
    expect(screen.getByText(/2 critical alerts: AHT exceeded upper limit/i)).toBeInTheDocument();
    expect(screen.getByText('1 of 2')).toBeInTheDocument();
  });

  it('handles empty previous month and null scores gracefully', () => {
    render(
      <InsightsSummaryStrip
        story={{
          ...mockStory,
          current_score: null,
          score_change: null,
          gap_points: null,
        }}
        rows={[]}
        criticalInsights={[]}
        onOpenInsight={vi.fn()}
      />
    );

    const section = screen.getByRole('region', { name: 'Summary' });
    expect(section).toHaveTextContent('N/A');
    expect(section).toHaveTextContent('No previous month');
    expect(section).toHaveTextContent('0 of 0 KPIs below target');
  });
});
