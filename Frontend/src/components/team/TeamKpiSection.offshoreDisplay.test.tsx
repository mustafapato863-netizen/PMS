import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ThemeProvider } from '../../context/ThemeContext';
import TeamKpiSection from './TeamKpiSection';

// Synthetic Pre-Approvals IP Offshore month, shaped like the screenshot. Stored
// percent KPIs are ratios: 0.0026 is 0.26%, 0.01 is a 1% target.
const offshoreMetrics = {
  attendCR: 0,
  bookingCR: 0,
  avgAHT: '0:00',
  avgAHTSec: 0,
  abandonRate: 0,
  reachabilityRate: 0,
  totalBookings: 0,
  totalAttended: 0,
  totalCallsHandled: 0,
  totalAbandoned: 0,
  utzRate: 0,
  hasUtz: false,
  dynamicKpis: [
    {
      label: 'Controllable Rejection Rate',
      actual: 0.0026,
      target: 0.01,
      unit: '%',
      isLowerBetter: true,
      weight: 0.5,
      contribution: 50,
    },
    {
      label: 'Initial Error Rate',
      actual: 0.01626,
      target: 0.01,
      unit: '%',
      isLowerBetter: true,
      weight: 0.2,
      contribution: 12.3,
    },
    {
      label: 'Submission Rate',
      actual: 0.789,
      target: 0.9,
      unit: '%',
      weight: 0.3,
      contribution: 26.3,
    },
  ],
};

const renderOffshore = (metrics: typeof offshoreMetrics) => render(
  <ThemeProvider>
    <TeamKpiSection
      totalAgents={6}
      avgScore={70}
      pctAB={50}
      pctDE={0}
      classCounts={{ A: 1, B: 2, C: 2, D: 1, E: 0 }}
      isCallCenterView={false}
      isInbound={false}
      teamMetrics={metrics}
      prevTeamMetrics={null}
      avgAHTSec={0}
      teamId="pre-approvals-offshore"
      teamName="Pre-Approvals IP Offshore"
      month="September"
    />
  </ThemeProvider>,
);

describe('Pre-Approvals IP Offshore team cards show each percentage once', () => {
  it('shows the controllable rejection card at 0.26% against a 1.0% target', () => {
    renderOffshore(offshoreMetrics);
    const card = screen.getByText('Controllable Rejection Rate').closest('article');
    expect(card).toHaveTextContent('0.26%');
    expect(card).toHaveTextContent('≤ 1.0%');
    expect(card).toHaveTextContent('On Target');
    expect(card).toHaveTextContent('Contribution50.0%');
    expect(card).not.toHaveTextContent('≤ 100');
  });

  it('shows the initial error card at 1.6% against a 1.0% target, 61.5% of target', () => {
    renderOffshore(offshoreMetrics);
    const card = screen.getByText('Initial Error Rate').closest('article');
    expect(card).toHaveTextContent('1.6%');
    expect(card).toHaveTextContent('≤ 1.0%');
    expect(card).toHaveTextContent('Below Target');
    expect(card).toHaveTextContent('61.5% of target');
    expect(card).toHaveTextContent('Contribution12.3%');
  });

  it('shows the submission card at 78.9% against a 90% target, 87.7% of target', () => {
    renderOffshore(offshoreMetrics);
    const card = screen.getByText('Submission Rate').closest('article');
    expect(card).toHaveTextContent('78.9%');
    expect(card).toHaveTextContent('90%');
    expect(card).toHaveTextContent('87.7% of target');
    expect(card).toHaveTextContent('Contribution26.3%');
  });

  it('keeps two decimals for a percentage below one point and a 0.5% target', () => {
    renderOffshore({
      ...offshoreMetrics,
      dynamicKpis: [{
        label: 'Probe Rate',
        actual: 0.003,
        target: 0.005,
        unit: '%',
        isLowerBetter: true,
        weight: 0.5,
        contribution: 50,
      }],
    });
    const card = screen.getByText('Probe Rate').closest('article');
    expect(card).toHaveTextContent('0.30%');
    expect(card).toHaveTextContent('≤ 0.50%');
  });
});
